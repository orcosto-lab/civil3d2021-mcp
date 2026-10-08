"""
tools_corridors.py  -  Herramientas para corredores de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError, iter_com_collection

log = logging.getLogger("civil3d_mcp.tools.corridors")


def _info_region(region) -> dict[str, Any]:
    info: dict[str, Any] = {}
    for attr, clave in (
        ("Name", "nombre"),
        ("StartStation", "pk_inicio"),
        ("EndStation", "pk_fin"),
    ):
        try:
            info[clave] = getattr(region, attr)
        except Exception:
            pass
    try:
        ensamblaje = getattr(region, "AssemblyName", None)
        if ensamblaje:
            info["ensamblaje"] = str(ensamblaje)
    except Exception:
        pass
    return info


def _info_baseline(baseline) -> dict[str, Any]:
    info: dict[str, Any] = {}
    for attr, clave in (
        ("AlignmentName", "alineacion"),
        ("ProfileName", "perfil"),
        ("StartStation", "pk_inicio"),
        ("EndStation", "pk_fin"),
    ):
        try:
            info[clave] = getattr(baseline, attr)
        except Exception:
            pass
    try:
        regiones = iter_com_collection(baseline.BaselineRegions)
        info["regiones"] = [_info_region(r) for r in regiones]
    except Exception as exc:
        info["regiones_error"] = str(exc)
    return info


def _info_corredor(cor) -> dict[str, Any]:
    info: dict[str, Any] = {
        "nombre": cor.Name,
        "descripcion": getattr(cor, "Description", ""),
    }
    try:
        baselines = iter_com_collection(cor.Baselines)
        info["baselines"] = [_info_baseline(bl) for bl in baselines]
    except Exception as exc:
        info["baselines_error"] = str(exc)
    return info


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="list_corridors",
        description=(
            "Lista todos los corredores del dibujo con nombre, descripcion, baselines "
            "(alineacion y perfil asociados), regiones de cada baseline y el ensamblaje "
            "aplicado en cada region. "
            "NO PROBADA (ampliada 25/07/2026): la parte de nombre/descripcion ya "
            "funcionaba antes; el detalle de baselines/regiones/ensamblaje es nuevo y usa "
            "nombres de propiedad (AlignmentName, ProfileName, BaselineRegions, "
            "AssemblyName) tomados de la API .NET de Civil 3D y del proyecto civil3d_github, "
            "sin confirmar contra el objeto COM real via AeccXUiLand.AeccApplication - la "
            "guia legacy de COM y la guia .NET documentan superficies distintas y no "
            "siempre coinciden en nombres. Cada nivel (baseline/region/ensamblaje) falla "
            "solo para si mismo (queda como '<nivel>_error'), sin abortar el resto."
        ),
    )
    async def list_corridors() -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                try:
                    corridors = client._doc.Corridors
                except Exception:
                    return {
                        "total": 0,
                        "corredores": [],
                        "nota": "Corredores no disponibles en esta version",
                    }
                resultado = [_info_corredor(cor) for cor in iter_com_collection(corridors)]
                return {"total": len(resultado), "corredores": resultado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="listar_feature_lines_corredor",
        description=(
            "Lista las feature lines generadas por un corredor a lo largo de su baseline "
            "principal (ej. borde de calzada, cuneta...), agrupadas por codigo, con las "
            "coordenadas XYZ de cada punto. "
            "LECCION: `Baseline.MainBaselineFeatureLines.FeatureLinesCol` (coleccion de "
            "colecciones de `AeccFeatureLine`, cada una con `.CodeName` y "
            "`.FeatureLinePoints[i].XYZ`) confirmado en la guia oficial de desarrollo de "
            "Civil3D (Civil3D-DevGuide, 'Listing Feature Lines Along a Baseline') - a "
            "diferencia de `AlignmentName`/`ProfileName`/`BaselineRegions` en "
            "`list_corridors`, que siguen sin verificar. NO cubre feature lines "
            "independientes (creadas a mano o desde alineacion/corredor con 'Create "
            "Feature Line From...'): no se encontro un metodo COM legacy confirmado para "
            "crearlas ni listarlas fuera del contexto de un corredor; esa pieza queda "
            "pendiente para la migracion a pythonnet."
        ),
    )
    async def listar_feature_lines_corredor(nombre_corredor: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                try:
                    corridors = client._doc.Corridors
                except Exception:
                    return {"error": "Corredores no disponibles en esta version."}
                cor = None
                for c in iter_com_collection(corridors):
                    if c.Name == nombre_corredor:
                        cor = c
                        break
                if cor is None:
                    return {"error": f"Corredor '{nombre_corredor}' no encontrado."}

                baselines_info = []
                for bl in iter_com_collection(cor.Baselines):
                    bl_info: dict[str, Any] = {}
                    try:
                        bl_info["alineacion"] = bl.AlignmentName
                    except Exception:
                        pass
                    grupos_codigo = []
                    try:
                        for fl_col in iter_com_collection(bl.MainBaselineFeatureLines.FeatureLinesCol):
                            for fl in iter_com_collection(fl_col):
                                puntos = []
                                try:
                                    for p in iter_com_collection(fl.FeatureLinePoints):
                                        xyz = p.XYZ
                                        puntos.append({"x": xyz[0], "y": xyz[1], "z": xyz[2]})
                                except Exception as exc:
                                    bl_info.setdefault("puntos_error", str(exc))
                                grupos_codigo.append({
                                    "codigo": getattr(fl, "CodeName", None),
                                    "total_puntos": len(puntos),
                                    "puntos": puntos,
                                })
                    except Exception as exc:
                        bl_info["feature_lines_error"] = str(exc)
                    bl_info["feature_lines"] = grupos_codigo
                    baselines_info.append(bl_info)

                return {"corredor": nombre_corredor, "baselines": baselines_info}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
