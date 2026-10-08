"""
tools_solidos.py  -  Solidificacion de perfiles de viga (polilineas/lineas) mediante EXTRUDE

Problema que resuelve: EXTRUDE exige un perfil cerrado Y exactamente coplanar para
producir un AcDb3dSolid; si el perfil esta cerrado pero con vertices ligeramente
alabeados (aunque sean pocos mm de desviacion), AutoCAD genera un AcDbExtrudedSurface
en su lugar, sin dar ningun error explicito. Ver 00_NOTAS_PROYECTO.md para el caso
real que origino esta herramienta (capa "05- Vigas", dibujo de produccion A, 15/07/2026).

solidificar_viga acepta 1 o 2 handles de origen:
  - 1 handle: una AcDb3dPolyline cerrada con 4 vertices unicos (rectangulo). Se corrige
    la planaridad definiendo el plano por los 3 primeros vertices y proyectando el 4o
    sobre ese plano (correccion minima, no minimos cuadrados).
  - 2 handles: dos segmentos abiertos de 2 vertices (AcDbLine o AcDb3dPolyline/2 vert),
    que representan los dos lados largos de la viga sin los lados cortos que cierren
    el rectangulo. Se reconstruye el rectangulo emparejando los extremos mas cercanos
    entre ambos segmentos, y se aplica la misma correccion de planaridad.

En ambos casos se crea una AcDb3dPolyline nueva y cerrada con los vertices corregidos,
se borran los objetos de origen (borrar_original=True por defecto) y se extruye la
nueva polilinea `altura` metros con EXTRUDE en modo Solido explicito (_MO _SO), por si
el modo de extrusion del dibujo hubiera quedado en Superficie. La direccion de la
extrusion es siempre perpendicular al plano corregido del perfil (perpendicular a los
lados cortos), que es lo correcto para vigas inclinadas: no hace falta indicar direccion,
EXTRUDE la toma del plano del perfil.
"""
from __future__ import annotations
import logging
import math
import time
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.solidos")


def _vertices_3d(obj) -> list[list[float]]:
    """Extrae vertices [x,y,z] de AcDbLine, AcDb3dPolyline, AcDbPolyline o AcDb2dPolyline."""
    tipo = obj.ObjectName
    if tipo == "AcDbLine":
        return [list(obj.StartPoint), list(obj.EndPoint)]
    coords = list(obj.Coordinates)
    if tipo == "AcDb3dPolyline":
        return [[coords[i*3], coords[i*3+1], coords[i*3+2]] for i in range(len(coords)//3)]
    elev = 0.0
    try:
        elev = float(obj.Elevation)
    except Exception:
        pass
    return [[coords[i*2], coords[i*2+1], elev] for i in range(len(coords)//2)]


def _dedupe_cierre(pts: list[list[float]], tol: float = 1e-6) -> list[list[float]]:
    """Si el primer y ultimo vertice coinciden (cierre repetido explicito), quita el ultimo."""
    if len(pts) > 1 and all(abs(pts[0][i] - pts[-1][i]) < tol for i in range(3)):
        return pts[:-1]
    return pts


def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _cross(a, b):
    return [a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]]


def _dot(a, b):
    return sum(a[i]*b[i] for i in range(3))


def _normalizar(a):
    m = math.sqrt(_dot(a, a))
    if m < 1e-12:
        return a
    return [x/m for x in a]


def _plano_por_3_forzar_4(pts4: list[list[float]]):
    """
    Define el plano por los 3 primeros vertices y proyecta el 4o sobre ese plano
    (correccion minima: solo se mueve el 4o vertice, a lo largo de la normal).
    Devuelve (pts_corregidos, normal, desviacion_original_m).
    """
    p0, p1, p2, p3 = pts4
    v1 = _sub(p1, p0)
    v2 = _sub(p2, p0)
    normal = _normalizar(_cross(v1, v2))
    d = _dot(_sub(p3, p0), normal)
    p3_corr = [p3[i] - d * normal[i] for i in range(3)]
    return [p0, p1, p2, p3_corr], normal, abs(d)


def _reconstruir_desde_2_lados(pts_a: list[list[float]], pts_b: list[list[float]]):
    """
    A partir de 2 lados largos sueltos (2 vertices cada uno), empareja los extremos
    mas cercanos y devuelve los 4 vertices en orden de rectangulo (sin cruce).
    """
    a0, a1 = pts_a
    b0, b1 = pts_b
    d_mismo = _dist(a0, b0) + _dist(a1, b1)
    d_cruzado = _dist(a0, b1) + _dist(a1, b0)
    if d_mismo <= d_cruzado:
        return [a0, a1, b1, b0]
    return [a0, a1, b0, b1]


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="solidificar_viga",
        description=(
            "Convierte un perfil de viga (1 o 2 handles) en un AcDb3dSolid extruido "
            "`altura` metros, perpendicular al plano corregido del perfil (correcto "
            "para vigas inclinadas, no hace falta indicar direccion). Con 1 handle: "
            "una AcDb3dPolyline cerrada de 4 vertices unicos; corrige planaridad "
            "definiendo el plano por los 3 primeros vertices y proyectando el 4o. "
            "Con 2 handles: dos segmentos abiertos de 2 vertices (AcDbLine o "
            "AcDb3dPolyline) que son los 2 lados largos de la viga sin cerrar; "
            "reconstruye el rectangulo emparejando extremos mas cercanos y aplica "
            "la misma correccion de planaridad. Crea una AcDb3dPolyline nueva y "
            "cerrada, borra los objetos de origen (salvo borrar_original=False), y "
            "extruye con EXTRUDE en modo Solido explicito (_MO _SO), por si el modo "
            "de extrusion del dibujo hubiera quedado en Superficie. "
            "LECCION: los 2 handles del modo de 2 segmentos deben ser los lados LARGOS "
            "(paralelos, proximos); con los lados cortos el emparejamiento puede cruzarse. "
            "LECCION: la direccion de extrusion no es consistente entre vigas del mismo lote - "
            "revisar visualmente tras cada lote y corregir a mano las invertidas. "
            "LECCION: esta tool va por SendCommand y puede fallar sin devolver error (EXTRUDE "
            "puede crear superficie en vez de solido) - tras ejecutarla, verificar el resultado "
            "real con leer_historial_comandos; si el registro esta desactivado, pedir "
            "autorizacion para activar_historial_comandos (nunca activarlo sin avisar)."
        ),
    )
    async def solidificar_viga(
        handles: list[str],
        altura: float = 0.20,
        capa_destino: str | None = None,
        borrar_original: bool = True,
    ) -> dict[str, Any]:
        try:
            def _run():
                if len(handles) not in (1, 2):
                    raise Civil3DError("Se requieren 1 o 2 handles (perfil cerrado, o 2 lados largos sueltos).")

                doc = client.active_doc
                ms = doc.ModelSpace

                objs = [doc.HandleToObject(h) for h in handles]
                capa_origen = objs[0].Layer

                diagnostico: dict[str, Any] = {"handles_origen": handles}

                if len(handles) == 1:
                    obj = objs[0]
                    if obj.ObjectName != "AcDb3dPolyline":
                        raise Civil3DError(
                            f"{handles[0]} no es AcDb3dPolyline (es {obj.ObjectName})."
                        )
                    pts = _dedupe_cierre(_vertices_3d(obj))
                    if len(pts) != 4:
                        raise Civil3DError(
                            f"{handles[0]} tiene {len(pts)} vertices unicos, se esperaban 4."
                        )
                    diagnostico["modo"] = "perfil_cerrado"
                else:
                    tipos_validos = ("AcDbLine", "AcDb3dPolyline", "AcDb2dPolyline", "AcDbPolyline")
                    grupos = []
                    for h, obj in zip(handles, objs):
                        if obj.ObjectName not in tipos_validos:
                            raise Civil3DError(f"{h}: tipo no soportado ({obj.ObjectName}).")
                        v = _vertices_3d(obj)
                        if len(v) != 2:
                            raise Civil3DError(f"{h}: se esperaban 2 vertices, hay {len(v)}.")
                        grupos.append(v)
                    long1 = _dist(*grupos[0])
                    long2 = _dist(*grupos[1])
                    if long1 > 1e-6 and abs(long1 - long2) / long1 > 0.02:
                        diagnostico["aviso"] = (
                            f"Los 2 lados largos difieren en longitud ({long1:.3f} m vs "
                            f"{long2:.3f} m) mas de un 2% - revisar emparejamiento."
                        )
                    pts = _reconstruir_desde_2_lados(grupos[0], grupos[1])
                    diagnostico["modo"] = "reconstruido_2_lados"
                    diagnostico["longitud_lado_1"] = round(long1, 4)
                    diagnostico["longitud_lado_2"] = round(long2, 4)

                pts_corr, normal, desviacion = _plano_por_3_forzar_4(pts)
                diagnostico["desviacion_planaridad_antes_m"] = round(desviacion, 5)
                diagnostico["normal_extrusion"] = [round(x, 4) for x in normal]

                flat = []
                for p in pts_corr + [pts_corr[0]]:
                    flat.extend(p)
                arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
                nueva_poly = ms.Add3DPoly(arr)
                try:
                    nueva_poly.Closed = True
                except Exception:
                    pass
                nueva_poly.Layer = capa_destino if capa_destino else capa_origen
                poly_handle = nueva_poly.Handle

                if borrar_original:
                    for obj in objs:
                        try:
                            obj.Delete()
                        except Exception:
                            pass

                cmd = (
                    f'(command "_EXTRUDE" "_MO" "_SO" '
                    f'(ssadd (handent "{poly_handle}") (ssadd)) "" {altura}) '
                )
                doc.SendCommand(cmd)
                time.sleep(1.0)

                resultado = ms.Item(ms.Count - 1)
                tipo_resultado = resultado.ObjectName

                return {
                    "success": tipo_resultado == "AcDb3dSolid",
                    "poly_intermedia_handle": poly_handle,
                    "resultado_handle": resultado.Handle,
                    "resultado_tipo": tipo_resultado,
                    "altura_extrusion": altura,
                    "capa": capa_destino if capa_destino else capa_origen,
                    **diagnostico,
                }
            return await run_com(_run)
        except Exception as exc:
            log.exception("solidificar_viga")
            return {"error": str(exc)}
