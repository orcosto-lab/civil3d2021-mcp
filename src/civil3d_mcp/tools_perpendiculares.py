"""
tools_perpendiculares.py  -  Generacion de perpendiculares con pendiente desde un eje (rasante)
hasta los bordes de calzada, para bombeo/peralte simple a dos aguas.

Metodo validado (14/07/2026): eje "Perfil" (AcDb3dPolyline con cota
real) + bordes "Calles" (2 AcDb3dPolyline). Genera 2 lineas 3D por estacion (izq/der),
cortando contra los bordes reales y aplicando una pendiente descendente constante desde
el eje. Estaciones = rejilla cada N metros + puntos donde la pendiente longitudinal del
eje cambia mas de un umbral (deteccion por ventana, no punto a punto, para evitar ruido
de levantamiento).
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.perpendiculares")


def _vertices_3d(obj) -> list[list[float]]:
    """Extrae vertices [x,y,z] de AcDb3dPolyline, AcDbPolyline o AcDb2dPolyline."""
    tipo = obj.ObjectName
    coords = list(obj.Coordinates)
    if tipo == "AcDb3dPolyline":
        return [[coords[i*3], coords[i*3+1], coords[i*3+2]] for i in range(len(coords)//3)]
    else:
        elev = 0.0
        try:
            elev = float(obj.Elevation)
        except Exception:
            pass
        return [[coords[i*2], coords[i*2+1], elev] for i in range(len(coords)//2)]


def _cum_dist(pts: list[list[float]]) -> list[float]:
    s = [0.0]
    for i in range(1, len(pts)):
        x0, y0, _ = pts[i-1]
        x1, y1, _ = pts[i]
        s.append(s[-1] + math.hypot(x1-x0, y1-y0))
    return s


def _ray_segment_intersect(p0, dvec, a, b):
    ax, ay = a
    bx, by = b
    ex, ey = bx-ax, by-ay
    denom = dvec[0]*ey - dvec[1]*ex
    if abs(denom) < 1e-9:
        return None
    diffx, diffy = ax-p0[0], ay-p0[1]
    t = (diffx*ey - diffy*ex)/denom
    u = (diffx*dvec[1] - diffy*dvec[0])/denom
    if t > 1e-6 and 0.0 <= u <= 1.0:
        return t
    return None


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="generar_perpendiculares",
        description=(
            "Genera lineas 3D perpendiculares a un eje (AcDb3dPolyline con cota real, tipo "
            "rasante/perfil) cada N metros y en los puntos donde la pendiente longitudinal "
            "cambia de forma sensible (deteccion por ventana, no vertice a vertice, para no "
            "confundir ruido de levantamiento con cambios reales). Cada perpendicular corta "
            "contra las polilineas de una capa de bordes (p.ej. bordes de calzada) y aplica "
            "una pendiente transversal constante descendente desde el eje hacia cada lado "
            "(bombeo/peralte simple a dos aguas). Si algun extremo del eje no tiene borde "
            "definido en esa zona, aproxima el ancho con el del punto valido mas cercano del "
            "mismo lado. Crea 2 lineas (izq/der) por estacion en la capa destino."
        ),
    )
    async def generar_perpendiculares(
        handle_eje: str,
        capa_bordes: str,
        distancia_estaciones: float = 5.0,
        umbral_pendiente: float = 1.5,
        ventana_deteccion: float = 3.0,
        pendiente_pct: float = 2.0,
        capa_destino: str = "IA",
        longitud_max_busqueda: float = 40.0,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        handle_eje : str
            Handle del AcDb3dPolyline del eje (rasante), con cota Z real.
        capa_bordes : str
            Nombre de la capa que contiene las polilineas de borde (calzada, aceras...).
        distancia_estaciones : float
            Separacion en metros de la rejilla de estaciones base.
        umbral_pendiente : float
            Diferencia minima (en %) entre la pendiente longitudinal antes/despues de un
            punto para considerarlo "notorio" y anadir una estacion extra ahi.
        ventana_deteccion : float
            Semi-ventana (en metros) usada para calcular la pendiente local antes/despues
            de cada punto candidato (evita el ruido de vertices muy proximos).
        pendiente_pct : float
            Pendiente transversal aplicada hacia abajo a cada lado (2.0 = 2%).
        capa_destino : str
            Capa donde se crean las lineas generadas (se crea si no existe).
        longitud_max_busqueda : float
            Longitud maxima (m) del rayo perpendicular al buscar interseccion con bordes.
        """
        try:
            def _run():
                doc = client.active_doc
                ms = client.model_space

                eje_obj = doc.HandleToObject(handle_eje)
                if eje_obj.ObjectName != "AcDb3dPolyline":
                    raise Civil3DError(
                        f"handle_eje {handle_eje} no es AcDb3dPolyline (es {eje_obj.ObjectName})."
                    )
                perfil = _vertices_3d(eje_obj)
                if len(perfil) < 2:
                    raise Civil3DError("El eje tiene menos de 2 vertices.")

                bordes = []
                for obj in ms:
                    try:
                        if obj.Layer.lower() != capa_bordes.lower():
                            continue
                        if obj.ObjectName in ("AcDb3dPolyline", "AcDbPolyline", "AcDb2dPolyline"):
                            bordes.append(_vertices_3d(obj))
                    except Exception:
                        continue
                if not bordes:
                    raise Civil3DError(f"No se encontraron polilineas en la capa '{capa_bordes}'.")

                S = _cum_dist(perfil)
                L = S[-1]

                def pos_at(s: float):
                    s = max(0.0, min(L, s))
                    lo, hi = 0, len(S) - 1
                    while lo < hi - 1:
                        mid = (lo + hi) // 2
                        if S[mid] <= s:
                            lo = mid
                        else:
                            hi = mid
                    s0, s1 = S[lo], S[hi]
                    t = 0.0 if s1 - s0 < 1e-9 else (s - s0) / (s1 - s0)
                    x0, y0, z0 = perfil[lo]
                    x1, y1, z1 = perfil[hi]
                    return (x0 + t*(x1-x0), y0 + t*(y1-y0), z0 + t*(z1-z0))

                def tangent_at(s: float, eps: float = 0.5):
                    a = pos_at(s - eps)
                    b = pos_at(s + eps)
                    dx, dy = b[0]-a[0], b[1]-a[1]
                    n = math.hypot(dx, dy)
                    return (dx/n, dy/n) if n > 0 else (1.0, 0.0)

                # deteccion de puntos notorios (cambio de pendiente longitudinal)
                notorios_raw = []
                for s in S:
                    if s < ventana_deteccion or s > L - ventana_deteccion:
                        continue
                    z_antes = pos_at(s - ventana_deteccion)[2]
                    z_aqui = pos_at(s)[2]
                    z_despues = pos_at(s + ventana_deteccion)[2]
                    p_antes = (z_aqui - z_antes) / ventana_deteccion * 100
                    p_despues = (z_despues - z_aqui) / ventana_deteccion * 100
                    delta = abs(p_despues - p_antes)
                    if delta > umbral_pendiente:
                        notorios_raw.append((s, delta))
                notorios_raw.sort()
                merged = []
                for s, delta in notorios_raw:
                    if merged and s - merged[-1][0] < 3.0:
                        if delta > merged[-1][1]:
                            merged[-1] = (s, delta)
                    else:
                        merged.append((s, delta))
                notorios_s = [s for s, _ in merged]

                grid = []
                s = 0.0
                while s < L:
                    grid.append(s)
                    s += distancia_estaciones
                grid.append(L)

                todas = sorted(grid + notorios_s)
                estaciones = []
                for s in todas:
                    if estaciones and s - estaciones[-1] < 0.5:
                        continue
                    estaciones.append(s)

                def find_intersection(center_xy, dir_xy):
                    best_t = None
                    for borde in bordes:
                        for i in range(1, len(borde)):
                            a = (borde[i-1][0], borde[i-1][1])
                            b = (borde[i][0], borde[i][1])
                            t = _ray_segment_intersect(center_xy, dir_xy, a, b)
                            if t is not None and t <= longitud_max_busqueda:
                                if best_t is None or t < best_t:
                                    best_t = t
                    return best_t

                crudos = []
                for s in estaciones:
                    cx, cy, cz = pos_at(s)
                    tx, ty = tangent_at(s)
                    perp = (-ty, tx)
                    for lado, sign in (("izq", 1.0), ("der", -1.0)):
                        dirv = (perp[0]*sign, perp[1]*sign)
                        t = find_intersection((cx, cy), dirv)
                        crudos.append([s, lado, cx, cy, cz, dirv, t])

                sin_dato = 0
                for item in crudos:
                    if item[6] is None:
                        s0, lado0 = item[0], item[1]
                        candidatos = sorted(
                            ((abs(it[0]-s0), it[6]) for it in crudos if it[1] == lado0 and it[6] is not None),
                            key=lambda x: x[0],
                        )
                        if candidatos:
                            item[6] = candidatos[0][1]
                            item.append("aproximado")
                        else:
                            item.append("sin_dato")
                            sin_dato += 1
                    else:
                        item.append("real")

                # crear capa destino si no existe
                try:
                    doc.Layers.Item(capa_destino)
                except Exception:
                    nueva = doc.Layers.Add(capa_destino)
                    nueva.color = 4

                resultados = []
                creadas = 0
                for s, lado, cx, cy, cz, dirv, t, origen in crudos:
                    if origen == "sin_dato":
                        resultados.append({"estacion": round(s, 3), "lado": lado, "origen": origen})
                        continue
                    ex = cx + dirv[0]*t
                    ey = cy + dirv[1]*t
                    ez = cz - (pendiente_pct/100.0)*t
                    p1 = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [cx, cy, cz])
                    p2 = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [ex, ey, ez])
                    linea = ms.AddLine(p1, p2)
                    linea.Layer = capa_destino
                    creadas += 1
                    resultados.append({
                        "estacion": round(s, 3), "lado": lado, "d": round(t, 3),
                        "origen": origen, "handle": linea.Handle,
                    })

                return {
                    "success": True,
                    "longitud_eje": round(L, 3),
                    "puntos_notorios": [round(x, 3) for x in notorios_s],
                    "estaciones_totales": len(estaciones),
                    "lineas_creadas": creadas,
                    "sin_dato": sin_dato,
                    "capa_destino": capa_destino,
                    "resultados": resultados,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
