"""
tools_geometria.py  -  Calculos geometricos: bounding box y encaje de bloques sobre superficies
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.geometria")


def _bbox_local_definicion(doc, nombre_efectivo: str) -> tuple[list[float], list[float]]:
    """
    Calcula el bounding box combinado de todas las entidades de una definicion
    de bloque (AcadBlock), en coordenadas LOCALES del bloque (sin transformar
    por insercion/escala/rotacion). Itera entidad por entidad porque AcadBlock
    no expone GetBoundingBox propio.
    """
    bloque_def = doc.Blocks(nombre_efectivo)
    min_acc = [float("inf"), float("inf"), float("inf")]
    max_acc = [float("-inf"), float("-inf"), float("-inf")]
    encontrado = False
    for ent in bloque_def:
        try:
            mn, mx = ent.GetBoundingBox()
        except Exception:
            continue  # entidades sin extents finitos (p.ej. attdefs ocultas)
        mn, mx = list(mn), list(mx)
        for k in range(3):
            min_acc[k] = min(min_acc[k], mn[k])
            max_acc[k] = max(max_acc[k], mx[k])
        encontrado = True
    if not encontrado:
        raise Civil3DError(
            f"No se pudo calcular bounding box local: la definicion '{nombre_efectivo}' "
            "no tiene entidades con extents finitos."
        )
    return min_acc, max_acc


def _esquinas_reales_rotadas(
    min_local: list[float],
    max_local: list[float],
    insercion: list[float],
    rotacion_rad: float,
    escala_x: float,
    escala_y: float,
) -> list[list[float]]:
    """
    Transforma las 4 esquinas en planta del bbox local (escala -> rotacion Z ->
    traslacion por punto de insercion) para obtener su posicion real en WCS.
    Asume rotacion solo en Z (sin inclinacion 3D), segun lo confirmado por el usuario.
    """
    esquinas_locales = [
        (min_local[0], min_local[1]),
        (max_local[0], min_local[1]),
        (max_local[0], max_local[1]),
        (min_local[0], max_local[1]),
    ]
    cos_r = math.cos(rotacion_rad)
    sin_r = math.sin(rotacion_rad)
    esquinas_wcs = []
    for lx, ly in esquinas_locales:
        # 1. escala
        sx = lx * escala_x
        sy = ly * escala_y
        # 2. rotacion Z (antihoraria, sentido AutoCAD)
        rx = sx * cos_r - sy * sin_r
        ry = sx * sin_r + sy * cos_r
        # 3. traslacion por punto de insercion
        wx = rx + insercion[0]
        wy = ry + insercion[1]
        esquinas_wcs.append([wx, wy])
    return esquinas_wcs


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="obtener_bounding_box",
        description=(
            "Devuelve el bounding box real (min/max X,Y,Z en WCS) de un objeto "
            "identificado por su handle, via GetBoundingBox COM. Funciona con "
            "cualquier entidad con extents finitos: AcDbBlockReference, polilineas, "
            "lineas, etc. AVISO: si el objeto es un AcDbBlockReference ROTADO en "
            "planta, este bounding box esta alineado a los ejes WCS y por tanto NO "
            "coincide con las esquinas reales del bloque (sera mas grande que la "
            "huella real). Para bloques rotados usar encajar_bloque_en_superficie, "
            "que calcula la huella real rotada."
        ),
    )
    async def obtener_bounding_box(handle: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                obj = doc.HandleToObject(handle)
                min_pt, max_pt = obj.GetBoundingBox()
                return {
                    "handle": handle,
                    "tipo": obj.ObjectName,
                    "min": list(min_pt),
                    "max": list(max_pt),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="encajar_bloque_en_superficie",
        description=(
            "Eleva un bloque (AcDbBlockReference) en Z, sin modificar sus coordenadas "
            "X/Y, hasta que su cara superior quede tangente por debajo de una "
            "superficie TIN, en el punto mas desfavorable. Calcula la huella REAL del "
            "bloque (respetando rotacion en planta y escala X/Y) a partir de la "
            "definicion de bloque, no del bounding box alineado a ejes WCS, evitando "
            "sobre-estimar el area en bloques rotados. Muestrea la superficie en las 4 "
            "esquinas reales del rectangulo rotado, toma la elevacion minima, y "
            "desplaza el bloque en Z para que su cara superior coincida con esa cota "
            "(menos la holgura indicada). Asume rotacion solo en el eje Z (sin "
            "inclinacion 3D del bloque). Util para encajar cajones, arquetas o "
            "estructuras prefabricadas bajo una superficie de terreno o forjado."
        ),
    )
    async def encajar_bloque_en_superficie(
        handle_bloque: str,
        nombre_superficie: str,
        holgura: float = 0.0,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        handle_bloque : str
            Handle del AcDbBlockReference a elevar.
        nombre_superficie : str
            Nombre exacto de la superficie TIN (case-sensitive).
        holgura : float
            Margen adicional a restar a la cota de encaje, para dejar el cajon
            estrictamente por debajo de la superficie en vez de tangente (mismas
            unidades que el dibujo).
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")

                doc = client.active_doc
                obj = doc.HandleToObject(handle_bloque)
                if obj.ObjectName != "AcDbBlockReference":
                    raise Civil3DError(
                        f"El handle {handle_bloque} no es un AcDbBlockReference "
                        f"(es {obj.ObjectName})."
                    )

                # Z superior real del bloque ya insertado (no depende de la
                # rotacion en planta, solo de rotacion 3D, que se asume nula)
                _, max_pt_wcs = obj.GetBoundingBox()
                z_top_actual = list(max_pt_wcs)[2]

                nombre_efectivo = obj.EffectiveName
                insercion = list(obj.InsertionPoint)
                rotacion_rad = obj.Rotation
                escala_x = obj.XScaleFactor
                escala_y = obj.YScaleFactor

                min_local, max_local = _bbox_local_definicion(doc, nombre_efectivo)
                esquinas_wcs = _esquinas_reales_rotadas(
                    min_local, max_local, insercion, rotacion_rad, escala_x, escala_y
                )

                surf = None
                for s in client._doc.Surfaces:
                    if s.Name == nombre_superficie:
                        surf = s
                        break
                if surf is None:
                    raise Civil3DError(f"Superficie '{nombre_superficie}' no encontrada.")

                puntos_muestreados = []
                for ex, ey in esquinas_wcs:
                    elev = surf.FindElevationAtXY(ex, ey)
                    puntos_muestreados.append([ex, ey, elev])

                punto_desfavorable = min(puntos_muestreados, key=lambda p: p[2])
                elev_minima = punto_desfavorable[2]
                z_objetivo = elev_minima - holgura
                dz = z_objetivo - z_top_actual

                pt_base = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0, 0.0, 0.0]
                )
                pt_dest = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0, 0.0, dz]
                )
                obj.Move(pt_base, pt_dest)

                return {
                    "success": True,
                    "handle": handle_bloque,
                    "superficie": nombre_superficie,
                    "rotacion_grados": math.degrees(rotacion_rad),
                    "esquinas_reales_evaluadas": puntos_muestreados,
                    "elevacion_minima_superficie": elev_minima,
                    "punto_mas_desfavorable_xy": punto_desfavorable[:2],
                    "holgura_aplicada": holgura,
                    "z_top_antes": z_top_actual,
                    "z_top_despues": z_objetivo,
                    "dz_aplicado": dz,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
