"""
tools_asignar_z.py  -  Asigna cota Z a vertices de lineas/polilineas desde
puntos COGO por coincidencia XY.
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError, con_reintentos

log = logging.getLogger("civil3d_mcp.tools.asignar_z")

TIPOS_SOPORTADOS = ("AcDbLine", "AcDbPolyline", "AcDb3dPolyline")


def _leer_puntos_cogo(client: Civil3DClient) -> list[dict]:
    puntos_col = client._get_cogo_collection()
    if puntos_col is None:
        raise Civil3DError(
            "No se pudo acceder a la coleccion de puntos COGO (Document.Points)."
        )
    puntos = []
    for pt in puntos_col:
        try:
            puntos.append({
                "numero": pt.Number,
                "este": float(pt.Easting),
                "norte": float(pt.Northing),
                "elevacion": float(pt.Elevation),
            })
        except Exception:
            pass
    return puntos


def _mas_cercano(x: float, y: float, puntos: list[dict], tolerancia: float):
    """Punto COGO mas cercano en XY dentro de tolerancia, o None."""
    mejor = None
    mejor_d2 = tolerancia * tolerancia
    for p in puntos:
        dx = p["este"] - x
        dy = p["norte"] - y
        d2 = dx * dx + dy * dy
        if d2 <= mejor_d2:
            mejor_d2 = d2
            mejor = p
    return mejor


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="asignar_z_desde_cogo",
        description=(
            "Asigna a cada vertice de linea/polilinea la cota Z del punto COGO cuya "
            "posicion XY coincida dentro de una tolerancia. Recorre AcDbLine "
            "(inicio/fin), AcDb3dPolyline (cada vertice) y AcDbPolyline 2D en las "
            "capas indicadas. "
            "LECCION: AcDbPolyline (LWPOLYLINE 2D) solo tiene una Elevation global "
            "para toda la entidad, no Z por vertice -- por eso esta tool SIEMPRE "
            "convierte primero cualquier AcDbPolyline de las capas indicadas a "
            "AcDb3dPolyline (via ms.Add3DPoly, patron ya probado en "
            "solidificar_viga), preservando su Elevation original como Z base antes "
            "de aplicar las coincidencias; el handle cambia y se reporta el mapeo "
            "original->nuevo en 'conversiones_2d_a_3d'. "
            "Coincidencia: para cada vertice se busca el punto COGO mas cercano en "
            "XY dentro de 'tolerancia' (por defecto 0.001 m); si no hay ninguno "
            "dentro de tolerancia, el vertice se deja igual (no se pisa con 0 ni "
            "con ningun otro valor). Por defecto (confirmar=False) NO modifica "
            "nada -- solo devuelve el recuento de vertices que se asignarian, las "
            "conversiones 2D->3D que se harian y la lista de entidades con "
            "vertices sin coincidencia para revisar antes de aplicar; repetir con "
            "confirmar=True para aplicar de verdad. PENDIENTE/RIESGO NO PROBADO: "
            "la reasignacion de StartPoint/EndPoint (linea) y Coordinates "
            "(polilinea 3D existente) via VARIANT COM directo sobre una entidad ya "
            "creada no tiene precedente confirmado en este proyecto (tools_lines.py "
            "evita VARIANTs en creacion por riesgo de bloqueo COM con SendCommand "
            "en su lugar; ms.Add3DPoly para CREAR si esta probado en "
            "solidificar_viga, pero eso es distinto de reescribir Coordinates de "
            "un objeto existente). Verificar el resultado real con "
            "get_geometria_handles tras cada aplicacion con confirmar=True."
        ),
    )
    async def asignar_z_desde_cogo(
        capas: list[str] | None = None,
        tolerancia: float = 0.001,
        confirmar: bool = False,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        capas : list[str] | None
            Capas de ModelSpace a procesar. Por defecto ["0", "00_Muros"].
        tolerancia : float
            Distancia maxima XY (metros) para considerar coincidencia con un
            punto COGO. Se toma siempre el punto COGO mas cercano dentro de
            esa distancia.
        confirmar : bool
            False (por defecto): vista previa, no modifica el dibujo.
            True: aplica los cambios de verdad.
        """
        try:
            def _run():
                capas_uso = capas if capas else ["0", "00_Muros"]
                capas_lower = {c.lower() for c in capas_uso}
                puntos = con_reintentos(lambda: _leer_puntos_cogo(client))
                if not puntos:
                    return {"error": "No se encontraron puntos COGO en el dibujo."}

                ms = client.model_space

                def _filtrar_objetivos():
                    result = []
                    for obj in ms:
                        try:
                            if obj.Layer.lower() not in capas_lower:
                                continue
                            if obj.ObjectName not in TIPOS_SOPORTADOS:
                                continue
                            result.append(obj)
                        except Exception:
                            pass
                    return result

                objetivos = con_reintentos(_filtrar_objetivos)

                conversiones = []
                resumen = {
                    "AcDbLine": {"total": 0, "vertices_con_z": 0, "vertices_sin_match": 0},
                    "AcDb3dPolyline": {"total": 0, "vertices_con_z": 0, "vertices_sin_match": 0},
                    "AcDbPolyline_convertidas": {"total": 0, "vertices_con_z": 0, "vertices_sin_match": 0},
                }
                entidades_con_pendientes = []
                pendientes_2d = []

                # --- Paso 1: lineas y 3D polylines existentes ---
                for obj in objetivos:
                    tipo = obj.ObjectName
                    if tipo == "AcDbPolyline":
                        pendientes_2d.append(obj)
                        continue

                    if tipo == "AcDbLine":
                        try:
                            inicio = list(obj.StartPoint)
                            fin = list(obj.EndPoint)
                        except Exception as exc:
                            log.warning(f"No se pudo leer {obj.Handle}: {exc}")
                            continue
                        m1 = _mas_cercano(inicio[0], inicio[1], puntos, tolerancia)
                        m2 = _mas_cercano(fin[0], fin[1], puntos, tolerancia)
                        con_z = int(m1 is not None) + int(m2 is not None)
                        sin_match = 2 - con_z
                        resumen["AcDbLine"]["total"] += 1
                        resumen["AcDbLine"]["vertices_con_z"] += con_z
                        resumen["AcDbLine"]["vertices_sin_match"] += sin_match
                        if sin_match:
                            entidades_con_pendientes.append({
                                "handle": obj.Handle, "tipo": tipo, "capa": obj.Layer,
                                "total_vertices": 2, "sin_match": sin_match,
                            })
                        if confirmar and con_z:
                            if m1:
                                inicio[2] = m1["elevacion"]
                            if m2:
                                fin[2] = m2["elevacion"]
                            try:
                                obj.StartPoint = win32com.client.VARIANT(
                                    pythoncom.VT_ARRAY | pythoncom.VT_R8, inicio)
                                obj.EndPoint = win32com.client.VARIANT(
                                    pythoncom.VT_ARRAY | pythoncom.VT_R8, fin)
                            except Exception as exc:
                                log.warning(f"No se pudo escribir {obj.Handle}: {exc}")

                    elif tipo == "AcDb3dPolyline":
                        try:
                            raw = list(obj.Coordinates)
                        except Exception as exc:
                            log.warning(f"No se pudo leer Coordinates {obj.Handle}: {exc}")
                            continue
                        n = len(raw) // 3
                        con_z = 0
                        nuevo = list(raw)
                        for i in range(n):
                            x, y = raw[3 * i], raw[3 * i + 1]
                            m = _mas_cercano(x, y, puntos, tolerancia)
                            if m:
                                con_z += 1
                                nuevo[3 * i + 2] = m["elevacion"]
                        sin_match = n - con_z
                        resumen["AcDb3dPolyline"]["total"] += 1
                        resumen["AcDb3dPolyline"]["vertices_con_z"] += con_z
                        resumen["AcDb3dPolyline"]["vertices_sin_match"] += sin_match
                        if sin_match:
                            entidades_con_pendientes.append({
                                "handle": obj.Handle, "tipo": tipo, "capa": obj.Layer,
                                "total_vertices": n, "sin_match": sin_match,
                            })
                        if confirmar and con_z:
                            try:
                                obj.Coordinates = win32com.client.VARIANT(
                                    pythoncom.VT_ARRAY | pythoncom.VT_R8, nuevo)
                            except Exception as exc:
                                log.warning(f"No se pudo escribir Coordinates {obj.Handle}: {exc}")

                # --- Paso 2: polilineas 2D -> SIEMPRE se convierten a 3D ---
                for obj in pendientes_2d:
                    handle_original = obj.Handle
                    try:
                        raw = list(obj.Coordinates)
                        elevacion_base = float(obj.Elevation)
                        cerrada = bool(obj.Closed)
                        capa_obj = obj.Layer
                    except Exception as exc:
                        log.warning(f"No se pudo leer polilinea 2D {handle_original}: {exc}")
                        continue
                    color_obj = None
                    linetype_obj = None
                    try:
                        color_obj = obj.Color
                    except Exception:
                        pass
                    try:
                        linetype_obj = obj.Linetype
                    except Exception:
                        pass

                    n = len(raw) // 2
                    con_z = 0
                    vertices_3d = []
                    for i in range(n):
                        x, y = raw[2 * i], raw[2 * i + 1]
                        m = _mas_cercano(x, y, puntos, tolerancia)
                        z = elevacion_base
                        if m:
                            con_z += 1
                            z = m["elevacion"]
                        vertices_3d.append((x, y, z))
                    sin_match = n - con_z

                    resumen["AcDbPolyline_convertidas"]["total"] += 1
                    resumen["AcDbPolyline_convertidas"]["vertices_con_z"] += con_z
                    resumen["AcDbPolyline_convertidas"]["vertices_sin_match"] += sin_match
                    if sin_match:
                        entidades_con_pendientes.append({
                            "handle": handle_original,
                            "tipo": "AcDbPolyline (se convertira a 3D)",
                            "capa": capa_obj, "total_vertices": n, "sin_match": sin_match,
                        })

                    if not confirmar:
                        conversiones.append({
                            "handle_original": handle_original,
                            "handle_nuevo": None,
                            "num_vertices": n,
                            "vertices_con_z": con_z,
                        })
                        continue

                    flat = []
                    for (x, y, z) in vertices_3d:
                        flat.extend([x, y, z])
                    try:
                        arr = win32com.client.VARIANT(
                            pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
                        nueva = ms.Add3DPoly(arr)
                        nueva.Layer = capa_obj
                        if cerrada:
                            try:
                                nueva.Closed = True
                            except Exception:
                                pass
                        if color_obj is not None:
                            try:
                                nueva.Color = color_obj
                            except Exception:
                                pass
                        if linetype_obj:
                            try:
                                nueva.Linetype = linetype_obj
                            except Exception:
                                pass
                        handle_nuevo = nueva.Handle
                        obj.Delete()
                        conversiones.append({
                            "handle_original": handle_original,
                            "handle_nuevo": handle_nuevo,
                            "num_vertices": n,
                            "vertices_con_z": con_z,
                        })
                    except Exception as exc:
                        conversiones.append({
                            "handle_original": handle_original,
                            "handle_nuevo": None,
                            "error": str(exc),
                        })

                total_con_z = sum(r["vertices_con_z"] for r in resumen.values())
                total_sin_match = sum(r["vertices_sin_match"] for r in resumen.values())

                return {
                    "modo": "aplicado" if confirmar else "vista_previa",
                    "capas": capas_uso,
                    "tolerancia": tolerancia,
                    "total_puntos_cogo": len(puntos),
                    "total_entidades_procesadas": len(objetivos),
                    "resumen_por_tipo": resumen,
                    "total_vertices_con_z_asignada": total_con_z,
                    "total_vertices_sin_coincidencia": total_sin_match,
                    "conversiones_2d_a_3d": conversiones,
                    "entidades_con_vertices_sin_match": entidades_con_pendientes,
                    "mensaje": (
                        "Vista previa -- no se ha modificado el dibujo. Repite con "
                        "confirmar=True para aplicar."
                        if not confirmar else
                        "Cambios aplicados. Verifica una muestra con get_geometria_handles."
                    ),
                }
            return await run_com(_run)
        except Exception as exc:
            log.exception("asignar_z_desde_cogo")
            return {"error": str(exc)}
