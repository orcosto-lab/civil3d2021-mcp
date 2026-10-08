"""
tools_lineas_muestreo.py  -  Lineas de muestreo transversal nativas de Civil 3D
(Sample Lines), asociadas a una alineacion, para generar secciones.

Complementa (no sustituye) el flujo manual existente de PSC sobre AcDbSection
(ver tools_cotas.py: acotar_seccion/detectar_seccion) - esta via crea objetos
nativos AeccSampleLineGroup/AeccSampleLine que Civil3D reconoce como tales
(secciones, vistas de seccion, etc.), en vez de un AcDbSection generico.
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError, iter_com_collection

log = logging.getLogger("civil3d_mcp.tools.lineas_muestreo")


def _buscar_alineacion(client: Civil3DClient, nombre: str):
    for alig in iter_com_collection(client._doc.AlignmentsSiteless):
        if alig.Name == nombre:
            return alig
    return None


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="crear_lineas_muestreo",
        description=(
            "Crea un grupo de lineas de muestreo (Sample Line Group) nativo de Civil3D "
            "sobre una alineacion, con una linea perpendicular cada intervalo_m metros. "
            "Opcionalmente asocia una superficie para que generen secciones. "
            "LECCION: confirmado en la guia oficial de desarrollo de Civil3D "
            "(Civil3D-DevGuide, 'Creating a Sample Line' + 'Defining Sample Lines'). Los "
            "3 estilos requeridos por `SampleLineGroups.Add` (GroupPlotStyle, "
            "SampleLineStyle, SampleLineLabelStyle) se toman como el PRIMERO disponible "
            "en el dibujo (`Item(0)`) siguiendo el mismo patron del ejemplo oficial ('el "
            "que sea, usamos el que ya tenga el dibujo') - si el dibujo no tiene ninguno "
            "de un tipo, esta tool falla con un error claro en vez de crear uno nuevo. "
            "NO se usa `AddByStationRange` (necesitaria instanciar un objeto "
            "`AeccStationRange` con ~10 propiedades y 2 enums COM sin valor confirmado): "
            "en su lugar, esta tool calcula las estaciones ella misma en Python y llama a "
            "`SampleLineGroup.SampleLines.AddByStation` una vez por estacion (metodo mas "
            "simple, sin enums, totalmente confirmado). Tope duro de 500 lineas de "
            "muestreo por llamada."
        ),
    )
    async def crear_lineas_muestreo(
        nombre_alineacion: str,
        nombre_grupo: str,
        intervalo_m: float,
        ancho_izquierda: float = 20.0,
        ancho_derecha: float = 20.0,
        capa: str = "0",
        nombre_superficie: str | None = None,
        pk_inicio: float | None = None,
        pk_fin: float | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        nombre_grupo : str
            Nombre del nuevo Sample Line Group.
        intervalo_m : float
            Separacion entre lineas de muestreo, en metros (minimo forzado: 1.0 m).
        ancho_izquierda, ancho_derecha : float
            Longitud de cada linea de muestreo a cada lado del eje, en metros.
        capa : str
            Capa donde se dibuja el grupo.
        nombre_superficie : str, opcional
            Si se indica, se asocia esa superficie al grupo (Sample=True) para generar
            secciones reales; si se omite, el grupo se crea sin superficies asociadas.
        pk_inicio, pk_fin : float, opcional
            Rango de PK a cubrir; por defecto, todo el rango de la alineacion.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}

                try:
                    group_plot_style = client._doc.GroupPlotStyles.Item(0)
                    sl_style = client._doc.SampleLineStyles.Item(0)
                    sl_label_style = client._doc.SampleLineLabelStyles.Item(0)
                except Exception as exc:
                    return {
                        "error": (
                            f"El dibujo no tiene estilos de GroupPlot/SampleLine/"
                            f"SampleLineLabel disponibles (se necesita al menos uno de "
                            f"cada uno ya existente): {exc}"
                        )
                    }

                try:
                    grupo = alig.SampleLineGroups.Add(
                        nombre_grupo, capa, group_plot_style, sl_style, sl_label_style
                    )
                except Exception as exc:
                    return {"error": f"No se pudo crear el grupo de lineas de muestreo: {exc}"}

                superficie_asociada = None
                if nombre_superficie:
                    surf = None
                    for s in iter_com_collection(client._doc.Surfaces):
                        if s.Name == nombre_superficie:
                            surf = s
                            break
                    if surf is None:
                        return {
                            "error": f"Superficie '{nombre_superficie}' no encontrada (grupo '{nombre_grupo}' ya creado sin superficie).",
                            "grupo_creado": nombre_grupo,
                        }
                    try:
                        section_style = client._doc.SectionStyles.Item(0)
                        sampled = grupo.SampledSurfaces.Add(surf, section_style)
                        sampled.Sample = True
                        superficie_asociada = nombre_superficie
                    except Exception as exc:
                        return {
                            "error": f"No se pudo asociar la superficie: {exc}",
                            "grupo_creado": nombre_grupo,
                        }

                pki = pk_inicio if pk_inicio is not None else alig.StartingStation
                pkf = pk_fin if pk_fin is not None else alig.EndingStation
                if pkf <= pki:
                    return {"error": "Rango de PK invalido (pk_fin <= pk_inicio)."}
                paso = max(1.0, intervalo_m)
                estaciones = []
                pk = pki
                while pk <= pkf:
                    estaciones.append(pk)
                    pk += paso
                if not estaciones or estaciones[-1] < pkf:
                    estaciones.append(pkf)
                if len(estaciones) > 500:
                    return {
                        "error": (
                            f"Se generarian {len(estaciones)} lineas de muestreo, por "
                            f"encima del tope de 500. Sube intervalo_m o reduce el rango "
                            f"de PK."
                        ),
                        "grupo_creado": nombre_grupo,
                    }

                creadas = []
                errores = []
                for i, pk_linea in enumerate(estaciones):
                    nombre_linea = f"{nombre_grupo}_{i:04d}_PK{pk_linea:.2f}"
                    try:
                        grupo.SampleLines.AddByStation(
                            nombre_linea, pk_linea, ancho_izquierda, ancho_derecha
                        )
                        creadas.append({"nombre": nombre_linea, "pk": pk_linea})
                    except Exception as exc:
                        errores.append({"pk": pk_linea, "error": str(exc)})

                return {
                    "success": True,
                    "alineacion": nombre_alineacion,
                    "grupo": nombre_grupo,
                    "superficie_asociada": superficie_asociada,
                    "total_lineas_creadas": len(creadas),
                    "total_errores": len(errores),
                    "lineas": creadas,
                    "errores": errores,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
