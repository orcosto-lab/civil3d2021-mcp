"""
tools_cotas.py  -  Anotacion de cotas de nivel sobre bloques de seccion generados

Flujo validado en dibujo de produccion B (03/07/2026):
Un bloque generado desde un plano de seccion (AcDbSection) esta a escala 1:1 y
su Y local es la altura sobre la Elevation del plano de seccion, por lo que
cota_real = Y_local + Elevation. Los puntos a acotar son las intersecciones
del plano vertical de corte con las aristas 3D del modelo (lineas y
polilineas 3D de las capas del modelo).
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.cotas")


def _cruce(a, b, L, p, q):
    """Interseccion de la banda vertical sobre el segmento 2D a->b con la
    arista 3D p->q. Devuelve (distancia_a_lo_largo, Z) o None."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ex, ey = q[0] - p[0], q[1] - p[1]
    den = dx * ey - dy * ex
    if abs(den) < 1e-12:
        return None
    t = ((ax - p[0]) * dy - (ay - p[1]) * dx) / (-den)
    if t < -1e-9 or t > 1 + 1e-9:
        return None
    cx, cy = p[0] + t * ex, p[1] + t * ey
    s = ((cx - ax) * dx + (cy - ay) * dy) / (L * L)
    if s < -1e-9 or s > 1 + 1e-9:
        return None
    return (s * L, p[2] + t * (q[2] - p[2]))


def _aristas_modelo(doc, capas_modelo):
    """Recolecta segmentos 3D (lineas y polilineas 3D) de las capas del modelo."""
    aristas = []
    for raw in doc.ModelSpace:
        try:
            obj = win32com.client.Dispatch(raw)
            on, capa = obj.ObjectName, obj.Layer
            if capa not in capas_modelo:
                continue
            if on == "AcDbLine":
                aristas.append((tuple(obj.StartPoint), tuple(obj.EndPoint)))
            elif on == "AcDb3dPolyline":
                c = list(obj.Coordinates)
                pts = [(c[i], c[i + 1], c[i + 2]) for i in range(0, len(c), 3)]
                aristas += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        except Exception:
            continue
    return aristas


def _intersecciones_dedup(seg, aristas, tol):
    """Intersecciones plano-modelo deduplicadas. seg = ((ax,ay),(bx,by))."""
    a, b = seg
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-9:
        return [], 0.0
    puntos = [r for p, q in aristas if (r := _cruce(a, b, L, p, q)) is not None]
    puntos.sort()
    dedup = []
    for d, z in puntos:
        if not any(abs(d - d0) < tol and abs(z - z0) < tol for d0, z0 in dedup):
            dedup.append((d, z))
    return dedup, L


def _vertices_bloque(doc, nombre_bloque):
    """Extremos (x,y) locales de las lineas de la definicion de bloque."""
    bdef = doc.Blocks.Item(nombre_bloque)
    vtx = []
    for raw in bdef:
        obj = win32com.client.Dispatch(raw)
        if obj.ObjectName == "AcDbLine":
            sp, ep = obj.StartPoint, obj.EndPoint
            vtx += [(sp[0], sp[1]), (ep[0], ep[1])]
    return vtx


def _calibrar(dedup, vtx, elev, tol):
    """Ajusta local_x = dir*d + offset casando alturas entre intersecciones y
    vertices del bloque. Devuelve (dir, offset, casados)."""
    mejor = None
    for dr in (1, -1):
        cands = {}
        for d, z in dedup:
            yl = z - elev
            for x, y in vtx:
                if abs(y - yl) < tol:
                    k = round((x - dr * d) / tol)
                    cands[k] = cands.get(k, 0) + 1
        if cands:
            k, score = max(cands.items(), key=lambda kv: kv[1])
            if mejor is None or score > mejor[2]:
                mejor = (dr, k * tol, score)
    if mejor is None:
        return None
    dr, off, _ = mejor
    difs = sorted(
        x - dr * d
        for d, z in dedup
        for x, y in vtx
        if abs(y - (z - elev)) < tol and abs((x - dr * d) - off) < 3 * tol
    )
    if difs:
        off = difs[len(difs) // 2]
    casados = sum(
        1 for d, z in dedup
        if any(abs(y - (z - elev)) < tol and abs(x - (dr * d + off)) < tol
               for x, y in vtx)
    )
    return (dr, off, casados)


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="acotar_seccion",
        description=(
            "Acota con MLeaders de nivel (elevacion Z real) un bloque de seccion "
            "generado desde un plano de seccion (AcDbSection). Calcula las "
            "intersecciones del plano vertical de corte con las aristas 3D del "
            "modelo (lineas y polilineas 3D de capas_modelo), deduce la "
            "transformacion al bloque 2D (cota = Y_local + Elevation del plano, "
            "calibrando el eje X automaticamente, incluidas vistas especulares "
            "con XScale=-1), y crea un MLeader por punto con la cota real. "
            "Requiere que el bloque este insertado sin rotacion y a escala "
            "unitaria (+-1). Si no se pasan vertices_seccion (la lectura COM "
            "externa de Section.Vertices falla con 'Violacion de bloqueo'), la "
            "linea de corte se deduce del bounding box de la seccion probando "
            "ambas diagonales y validando contra la geometria del bloque; solo "
            "valido para secciones rectas de 2 vertices. Aborta sin crear nada "
            "si menos del 80%% de los puntos casan con vertices del bloque. "
            "LECCION: las cotas se crean en amarillo (ACI 2) sobre capa_destino "
            "(IA por defecto); un casado alto NO garantiza que el cluster este "
            "completo -- reconstruir el grafo de lineas+splines del bloque y "
            "cruzarlo contra lo ya acotado antes de darlo por cerrado."
        ),
    )
    async def acotar_seccion(
        handle_seccion: str,
        handle_bloque: str,
        capas_modelo: list[str],
        capa_destino: str = "IA",
        tolerancia: float = 0.02,
        longitud_directriz: float = 0.5,
        decimales: int = 3,
        altura_texto: float = 0.2,
        vertices_seccion: list[float] | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        handle_seccion : handle del AcDbSection (plano de seccion).
        handle_bloque : handle del AcDbBlockReference del bloque de seccion generado.
        capas_modelo : capas cuyas lineas/polilineas 3D forman el modelo a cortar.
        capa_destino : capa de las cotas (se crea en cian si no existe).
        tolerancia : tolerancia de casado y deduplicado en metros.
        longitud_directriz : largo del tramo vertical del MLeader.
        decimales : decimales del texto de cota.
        altura_texto : altura del texto del MLeader.
        vertices_seccion : opcional [x1, y1, x2, y2] de la linea de corte en planta;
            si se omite se deduce del bounding box de la seccion.
        """
        try:
            def _run():
                doc = client.active_doc

                sec = doc.HandleToObject(handle_seccion)
                if sec.ObjectName != "AcDbSection":
                    raise Civil3DError(
                        f"{handle_seccion} no es AcDbSection (es {sec.ObjectName}).")
                elev = float(sec.Elevation)

                ref = doc.HandleToObject(handle_bloque)
                if ref.ObjectName != "AcDbBlockReference":
                    raise Civil3DError(
                        f"{handle_bloque} no es AcDbBlockReference (es {ref.ObjectName}).")
                if abs(abs(ref.XScaleFactor) - 1) > 1e-6 or abs(ref.YScaleFactor - 1) > 1e-6 \
                        or abs(ref.Rotation) > 1e-6:
                    raise Civil3DError(
                        "El bloque debe estar sin rotacion y con escalas +-1/1.")

                aristas = _aristas_modelo(doc, capas_modelo)
                if not aristas:
                    raise Civil3DError("Sin aristas 3D en las capas indicadas.")
                vtx = _vertices_bloque(doc, ref.EffectiveName)
                if not vtx:
                    raise Civil3DError("La definicion del bloque no tiene lineas.")

                # --- candidatos de linea de corte ---
                if vertices_seccion:
                    if len(vertices_seccion) != 4:
                        raise Civil3DError("vertices_seccion debe ser [x1,y1,x2,y2].")
                    x1, y1, x2, y2 = vertices_seccion
                    candidatos = [((x1, y1), (x2, y2))]
                else:
                    mn, mx = sec.GetBoundingBox()
                    mn, mx = list(mn), list(mx)
                    candidatos = [
                        ((mn[0], mn[1]), (mx[0], mx[1])),  # diagonal 1
                        ((mn[0], mx[1]), (mx[0], mn[1])),  # diagonal 2
                    ]

                # --- elegir candidato por casado con el bloque ---
                mejor = None
                for seg in candidatos:
                    dedup, L = _intersecciones_dedup(seg, aristas, tolerancia)
                    if len(dedup) < 2:
                        continue
                    cal = _calibrar(dedup, vtx, elev, tolerancia)
                    if cal is None:
                        continue
                    dr, off, casados = cal
                    ratio = casados / len(dedup)
                    if mejor is None or ratio > mejor["ratio"]:
                        mejor = {"seg": seg, "dedup": dedup, "dir": dr,
                                 "offset": off, "casados": casados,
                                 "ratio": ratio, "longitud": L}
                if mejor is None:
                    raise Civil3DError(
                        "El plano no corta el modelo (o no hay casado posible). "
                        "Revisar capas_modelo o pasar vertices_seccion.")
                if mejor["ratio"] < 0.8:
                    raise Civil3DError(
                        f"Solo casan {mejor['casados']}/{len(mejor['dedup'])} puntos "
                        "(<80%). No se crea nada. Probar con vertices_seccion "
                        "explicitos o revisar el emparejamiento seccion-bloque.")

                # --- capa destino ---
                existia = any(l.Name == capa_destino for l in doc.Layers)
                capa = doc.Layers.Add(capa_destino)
                if not existia:
                    capa.Color = 4  # cian, convencion de propuestas IA

                # --- crear MLeaders ---
                ins = list(ref.InsertionPoint)
                sx = ref.XScaleFactor
                dedup = mejor["dedup"]
                dr, off = mejor["dir"], mejor["offset"]
                ys_loc = [z - elev for _, z in dedup]
                mitad = (min(ys_loc) + max(ys_loc)) / 2.0
                ms = doc.ModelSpace
                cotas = []
                for d, z in dedup:
                    lx, ly = dr * d + off, z - elev
                    wx = ins[0] + sx * lx
                    wy = ins[1] + ly
                    wz = ins[2]
                    up = 1.0 if ly >= mitad else -1.0
                    pts = win32com.client.VARIANT(
                        pythoncom.VT_ARRAY | pythoncom.VT_R8,
                        [wx, wy, wz, wx, wy + up * longitud_directriz, wz])
                    ret = ms.AddMLeader(pts, 0)
                    # pywin32 devuelve (objeto, indice) por el out-param
                    ml = ret[0] if isinstance(ret, tuple) else ret
                    try:
                        ml.ContentType = 2  # acMTextContent
                    except Exception:
                        pass
                    ml.TextString = f"{z:.{decimales}f}"
                    try:
                        ml.TextHeight = altura_texto
                    except Exception:
                        pass
                    ml.Layer = capa_destino
                    try:
                        ml.Color = 2  # amarillo ACI, convencion de cotas (independiente de la capa)
                    except Exception:
                        pass
                    cotas.append({"handle": ml.Handle,
                                  "distancia": round(d, 3),
                                  "cota": round(z, decimales)})

                return {
                    "success": True,
                    "seccion": handle_seccion,
                    "bloque": handle_bloque,
                    "elevacion_base": elev,
                    "linea_corte": [round(c, 4) for p in mejor["seg"] for c in p],
                    "longitud_corte": round(mejor["longitud"], 3),
                    "calibracion": {"dir": dr, "offset": round(off, 4),
                                    "casados": f"{mejor['casados']}/{len(dedup)}"},
                    "capa": capa_destino,
                    "n_cotas": len(cotas),
                    "cotas": cotas,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="acotar_solidos_seccion",
        description=(
            "Acota con MLeaders de nivel (top y bottom reales) los solidos 3D "
            "(AcDb3dSolid, p.ej. vigas) que corta un tramo de seccion, usando "
            "Acad3DSolid.SectionSolid sobre cada solido de capa_solidos en vez de "
            "intersectar wireframe o mallas. La posicion local_x de cada solido "
            "es la distancia real a lo largo de vertices_seccion (offset=0, "
            "dir=1), leida del bounding box de la region resultante de "
            "SectionSolid; luego se calibra dir/offset casando esas alturas "
            "(top/bottom) contra los vertices 2D de la definicion del bloque, "
            "igual criterio que acotar_seccion -- el punto de insercion del "
            "bloque NO tiene por que coincidir con local_x=0. Como SectionSolid "
            "usa un plano infinito, cada solido se descarta si su distancia "
            "proyectada cae fuera de [0, longitud_del_tramo] (con un margen de "
            "tolerancia) -- asi los solidos de un tramo vecino con la misma "
            "orientacion de corte no se cuelan. Requiere el bloque de seccion "
            "sin rotacion y a escala unitaria (+-1), igual que acotar_seccion. "
            "A diferencia de acotar_seccion, vertices_seccion es obligatorio "
            "aqui: la deduccion automatica por bounding box del AcDbSection no "
            "es fiable para segmentos cortos o con solapes, y el coste de una "
            "cota mal emplazada en un elemento estructural (viga) es alto. "
            "Aborta sin crear nada si menos del 80%% de los puntos casan con "
            "vertices del bloque. LECCION: las cotas se crean en amarillo (ACI 2) "
            "sobre capa_destino (IA por defecto); corregido 19/08/2026 tras "
            "detectar cotas desplazadas en dibujo de produccion A -- version previa "
            "usaba insercion_bloque + local_x sin calibrar, valido solo si el "
            "bloque no tiene margen interno antes de la geometria del corte."
        ),
    )
    async def acotar_solidos_seccion(
        handle_bloque: str,
        vertices_seccion: list[float],
        capa_solidos: str,
        elevacion: float,
        capa_destino: str = "IA",
        tolerancia_rango: float = 0.05,
        tolerancia_calibracion: float = 0.02,
        longitud_directriz: float = 0.35,
        decimales: int = 3,
        altura_texto: float = 0.15,
        dimensiones: list[str] = ["top", "bottom"],
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        handle_bloque : handle del AcDbBlockReference del bloque de seccion generado.
        vertices_seccion : [x1, y1, x2, y2] de la linea de corte real en planta
            (obligatorio; leer Section.Vertices via LISP si falla por COM externo).
        capa_solidos : capa de los AcDb3dSolid a intersectar (p.ej. "Vigas 3D").
        elevacion : Elevation del AcDbSection asociado al tramo.
        capa_destino : capa de las cotas (se crea en cian si no existe).
        tolerancia_rango : margen en metros fuera de [0, longitud] antes de
            descartar un solido como perteneciente a un tramo vecino.
        tolerancia_calibracion : tolerancia en metros para casar alturas
            (top/bottom) contra los vertices del bloque al calibrar dir/offset.
        longitud_directriz : largo del tramo vertical del MLeader (hacia abajo).
        decimales : decimales del texto de cota.
        altura_texto : altura del texto del MLeader.
        dimensiones : cuales caras del solido acotar: "top", "bottom", o ambas.
        """
        try:
            def _run():
                doc = client.active_doc

                if len(vertices_seccion) != 4:
                    raise Civil3DError("vertices_seccion debe ser [x1,y1,x2,y2].")
                ax, ay, bx, by = vertices_seccion
                dx, dy = bx - ax, by - ay
                L = math.hypot(dx, dy)
                if L < 1e-6:
                    raise Civil3DError("vertices_seccion tiene longitud nula.")

                ref = doc.HandleToObject(handle_bloque)
                if ref.ObjectName != "AcDbBlockReference":
                    raise Civil3DError(
                        f"{handle_bloque} no es AcDbBlockReference (es {ref.ObjectName}).")
                if abs(abs(ref.XScaleFactor) - 1) > 1e-6 or abs(ref.YScaleFactor - 1) > 1e-6 \
                        or abs(ref.Rotation) > 1e-6:
                    raise Civil3DError(
                        "El bloque debe estar sin rotacion y con escalas +-1/1.")

                solidos = []
                for raw in doc.ModelSpace:
                    try:
                        obj = win32com.client.Dispatch(raw)
                        if obj.Layer == capa_solidos and obj.ObjectName == "AcDb3dSolid":
                            solidos.append(obj)
                    except Exception:
                        continue
                if not solidos:
                    raise Civil3DError(f"Sin AcDb3dSolid en la capa '{capa_solidos}'.")

                zmin_plano, zmax_plano = elevacion - 50.0, elevacion + 50.0
                p1 = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [ax, ay, zmin_plano])
                p2 = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [ax, ay, zmax_plano])
                p3 = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [bx, by, zmin_plano])

                # --- pasada 1: recoger (d, top, bottom) de cada solido sin crear nada ---
                crudos = []
                for solido in solidos:
                    try:
                        region = solido.SectionSolid(p1, p2, p3)
                    except Exception:
                        continue
                    if region is None:
                        continue
                    try:
                        mn, mx = region.GetBoundingBox()
                        mn, mx = list(mn), list(mx)
                    except Exception:
                        region.Delete()
                        continue
                    cx, cy = (mn[0] + mx[0]) / 2.0, (mn[1] + mx[1]) / 2.0
                    d = ((cx - ax) * dx + (cy - ay) * dy) / (L * L) * L
                    region.Delete()
                    if d < -tolerancia_rango or d > L + tolerancia_rango:
                        continue  # pertenece a un tramo vecino con la misma orientacion
                    crudos.append({"solido": solido, "d": d, "top": mx[2], "bottom": mn[2]})
                if not crudos:
                    raise Civil3DError(
                        "Ningun solido cae dentro de [0, longitud_del_tramo]. "
                        "Revisar vertices_seccion o capa_solidos.")

                # --- calibracion local_x -> bloque (mismo criterio que acotar_seccion) ---
                # LECCION: el punto de insercion del bloque no tiene por que
                # coincidir con local_x=0 de vertices_seccion (puede haber margen
                # interno). Se casa dir/offset por altura (top/bottom) contra los
                # vertices 2D de la definicion del bloque, no se asume offset=0.
                vtx = _vertices_bloque(doc, ref.EffectiveName)
                if not vtx:
                    raise Civil3DError("La definicion del bloque no tiene lineas.")
                puntos_cal = [(c["d"], z) for c in crudos for z in (c["top"], c["bottom"])]
                cal = _calibrar(puntos_cal, vtx, elevacion, tolerancia_calibracion)
                if cal is None:
                    raise Civil3DError(
                        "No se pudo calibrar local_x contra el bloque (sin alturas "
                        "coincidentes). Revisar elevacion, vertices_seccion o el bloque.")
                dr, off, casados = cal
                if casados / len(puntos_cal) < 0.8:
                    raise Civil3DError(
                        f"Solo casan {casados}/{len(puntos_cal)} puntos (<80%). "
                        "No se crea nada. Revisar vertices_seccion o el "
                        "emparejamiento bloque-solidos.")

                existia = any(l.Name == capa_destino for l in doc.Layers)
                capa = doc.Layers.Add(capa_destino)
                if not existia:
                    capa.Color = 4

                ins = list(ref.InsertionPoint)
                sx = ref.XScaleFactor
                ms = doc.ModelSpace
                cotas = []
                for c in crudos:
                    wx = ins[0] + sx * (dr * c["d"] + off)
                    wz = ins[2]
                    for cara, z in (("top", c["top"]), ("bottom", c["bottom"])):
                        if cara not in dimensiones:
                            continue
                        wy = ins[1] + (z - elevacion)
                        pts = win32com.client.VARIANT(
                            pythoncom.VT_ARRAY | pythoncom.VT_R8,
                            [wx, wy, wz, wx, wy - longitud_directriz, wz])
                        ret = ms.AddMLeader(pts, 0)
                        ml = ret[0] if isinstance(ret, tuple) else ret
                        try:
                            ml.ContentType = 2
                        except Exception:
                            pass
                        ml.TextString = f"{z:.{decimales}f}"
                        try:
                            ml.TextHeight = altura_texto
                        except Exception:
                            pass
                        ml.Layer = capa_destino
                        try:
                            ml.Color = 2  # amarillo ACI, convencion de cotas
                        except Exception:
                            pass
                        cotas.append({"handle": ml.Handle, "solido": c["solido"].Handle,
                                      "cara": cara, "distancia": round(c["d"], 3),
                                      "cota": round(z, decimales)})

                return {
                    "success": True,
                    "bloque": handle_bloque,
                    "capa_solidos": capa_solidos,
                    "elevacion_base": elevacion,
                    "longitud_corte": round(L, 3),
                    "calibracion": {"dir": dr, "offset": round(off, 4),
                                    "casados": f"{casados}/{len(puntos_cal)}"},
                    "capa": capa_destino,
                    "n_solidos_totales": len(solidos),
                    "n_cotas": len(cotas),
                    "cotas": cotas,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="detectar_seccion",
        description=(
            "Dada una capa de seccion (p.ej. '09 Seccion'), localiza en ella el/los "
            "AcDbSection y AcDbBlockReference generados y propone capas_modelo "
            "candidatas para acotar_seccion/acotar_solidos_seccion: capas de "
            "ModelSpace (distintas de capa_seccion) que contienen AcDbLine o "
            "AcDb3dPolyline, con su recuento, ordenadas de mas a menos lineas. "
            "Una sola pasada por ModelSpace en vez de listar_capas + "
            "listar_objetos capa a capa. Si encuentra exactamente 1 AcDbSection y "
            "1 AcDbBlockReference en la capa, los devuelve tambien como "
            "handle_seccion/handle_bloque listos para pasar directos; si hay mas "
            "de uno de cualquiera (varios tramos en la misma capa), NO empareja "
            "por su cuenta -- devuelve las listas completas en 'secciones'/"
            "'bloques' para que se elijan a mano. No decide capas_modelo por si "
            "sola, son solo candidatas: la eleccion final (y el criterio de que "
            "capas representan el modelo real) la hace quien acota."
        ),
    )
    async def detectar_seccion(
        capa_seccion: str,
        min_lineas: int = 1,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        capa_seccion : capa que contiene el AcDbSection y su bloque generado.
        min_lineas : descarta de las candidatas las capas con menos de este
            numero de AcDbLine/AcDb3dPolyline (ruido de geometria suelta).
        """
        try:
            def _run():
                doc = client.active_doc

                secciones, bloques, otros = [], [], []
                conteo: dict[str, int] = {}

                for raw in doc.ModelSpace:
                    try:
                        obj = win32com.client.Dispatch(raw)
                        capa, on = obj.Layer, obj.ObjectName
                    except Exception:
                        continue
                    if capa == capa_seccion:
                        if on == "AcDbSection":
                            secciones.append(obj.Handle)
                        elif on == "AcDbBlockReference":
                            bloques.append(obj.Handle)
                        else:
                            otros.append({"handle": obj.Handle, "tipo": on})
                    elif on in ("AcDbLine", "AcDb3dPolyline"):
                        conteo[capa] = conteo.get(capa, 0) + 1

                candidatas = sorted(
                    ({"capa": c, "n_lineas_3d": n} for c, n in conteo.items()
                     if n >= min_lineas),
                    key=lambda x: -x["n_lineas_3d"],
                )

                resultado: dict[str, Any] = {
                    "capa_seccion": capa_seccion,
                    "secciones": secciones,
                    "bloques": bloques,
                    "otros_objetos_en_capa": otros,
                    "capas_modelo_candidatas": candidatas,
                }
                if len(secciones) == 1 and len(bloques) == 1:
                    resultado["handle_seccion"] = secciones[0]
                    resultado["handle_bloque"] = bloques[0]
                    resultado["par_unico"] = True
                else:
                    resultado["par_unico"] = False
                    resultado["aviso"] = (
                        f"{len(secciones)} AcDbSection y {len(bloques)} "
                        f"AcDbBlockReference en '{capa_seccion}' -- no se "
                        "empareja automaticamente. Elegir los handles a mano de "
                        "'secciones'/'bloques'."
                    )
                return resultado
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
