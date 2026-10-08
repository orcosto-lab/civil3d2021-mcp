"""
tools_cogo.py  -  Herramientas para puntos COGO de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.cogo")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="listar_puntos_cogo",
        description="Lista los puntos COGO del dibujo (maximo 200). Devuelve numero, descripcion y coordenadas.",
    )
    async def listar_puntos_cogo() -> dict[str, Any]:
        try:
            def _run():
                points_col = client._get_cogo_collection()
                puntos = []
                if points_col is not None:
                    for pt in points_col:
                        try:
                            puntos.append({
                                "numero": pt.Number,
                                "descripcion": pt.RawDescription,
                                "norte": pt.Northing,
                                "este": pt.Easting,
                                "elevacion": pt.Elevation,
                            })
                        except Exception:
                            pass
                        if len(puntos) >= 200:
                            break
                else:
                    # Fallback: escanear ModelSpace
                    ms = client.model_space
                    for obj in ms:
                        if "CogoPoint" in obj.ObjectName or "AeccDb" in obj.ObjectName:
                            try:
                                puntos.append({
                                    "numero": obj.Number,
                                    "descripcion": obj.RawDescription,
                                    "norte": obj.Northing,
                                    "este": obj.Easting,
                                    "elevacion": obj.Elevation,
                                })
                            except Exception:
                                pass
                            if len(puntos) >= 200:
                                break
                return {"total": len(puntos), "puntos": puntos}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_punto_cogo",
        description="Crea un punto COGO en el dibujo con numero, descripcion y coordenadas.",
    )
    async def crear_punto_cogo(
        numero: int,
        norte: float,
        este: float,
        elevacion: float = 0.0,
        descripcion: str = "",
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        numero : int
            Numero del punto COGO.
        norte : float
            Coordenada Norte (Y).
        este : float
            Coordenada Este (X).
        elevacion : float
            Elevacion Z (por defecto 0).
        descripcion : str
            Descripcion raw del punto.
        """
        try:
            def _run():
                points_col = client._get_cogo_collection()
                if points_col is None:
                    raise Civil3DError("Civil 3D no disponible para crear puntos COGO.")
                # pts.Add requiere VARIANT array [Este, Norte, Elevacion] - orden critico
                coords = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [float(este), float(norte), float(elevacion)]
                )
                pt = points_col.Add(coords)
                if descripcion:
                    pt.RawDescription = descripcion
                pt.Number = numero
                return {
                    "success": True,
                    "numero": pt.Number,
                    "norte": pt.Northing,
                    "este": pt.Easting,
                    "elevacion": pt.Elevation,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="importar_puntos_cogo",
        description=(
            "Importa puntos COGO desde un archivo de texto (formato PENZD, PNEZ, ENZ, "
            "etc.) a la coleccion de puntos del dibujo. "
            "LECCION: `Document.Points.ImportPoints(ruta, formato, opciones)` confirmado "
            "en la guia oficial de desarrollo de Civil3D (Civil3D-DevGuide, 'Accessing "
            "Points in a File'); `formato` es un STRING LITERAL (no un enum), usa "
            "exactamente uno de: 'PENZD (space delimited)', 'PENZD (comma delimited)', "
            "'PENZ (space delimited)', 'PENZ (comma delimited)', 'PNEZD (space "
            "delimited)', 'PNEZD (comma delimited)', 'PNEZ (space delimited)', 'PNEZ "
            "(comma delimited)', 'ENZ (space delimited)', 'ENZ (comma delimited)', 'NEZ "
            "(space delimited)', 'NEZ (comma delimited)', 'PNE (space delimited)', 'PNE "
            "(comma delimited)', 'Autodesk Uploadable File'. PENDIENTE SIN RESOLVER: el "
            "3er parametro (`AeccPointImportOptions`, para resolucion de duplicados, "
            "grupo destino, offsets) es un objeto COM cuya forma de instanciarlo desde "
            "fuera de VBA no esta confirmada; esta tool intenta la llamada sin ese objeto "
            "(parametro omitido via `pythoncom.Missing`) y devuelve el error tal cual si "
            "Civil3D lo exige como obligatorio."
        ),
    )
    async def importar_puntos_cogo(ruta_archivo: str, formato: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                try:
                    puntos_col = client._doc.Points
                except Exception as exc:
                    return {"error": f"No se pudo acceder a Document.Points: {exc}"}
                try:
                    n = puntos_col.ImportPoints(ruta_archivo, formato, pythoncom.Missing)
                except Exception as exc:
                    return {
                        "error": (
                            f"ImportPoints fallo (puede exigir un objeto "
                            f"AeccPointImportOptions no soportado aqui, o el formato/ruta "
                            f"son invalidos): {exc}"
                        )
                    }
                return {"success": True, "ruta_archivo": ruta_archivo, "formato": formato, "puntos_importados": int(n)}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="exportar_puntos_cogo",
        description=(
            "Exporta todos los puntos COGO del dibujo a un archivo de texto. "
            "LECCION: `Document.Points.ExportPoints(ruta, formato, opciones)` confirmado "
            "en la misma guia oficial que `importar_puntos_cogo`; usa los mismos "
            "literales de formato. Mismo PENDIENTE que `importar_puntos_cogo` sobre el "
            "objeto de opciones (aqui `AeccPointExportOptions`): se omite via "
            "`pythoncom.Missing`."
        ),
    )
    async def exportar_puntos_cogo(ruta_archivo: str, formato: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                try:
                    puntos_col = client._doc.Points
                except Exception as exc:
                    return {"error": f"No se pudo acceder a Document.Points: {exc}"}
                try:
                    puntos_col.ExportPoints(ruta_archivo, formato, pythoncom.Missing)
                except Exception as exc:
                    return {
                        "error": (
                            f"ExportPoints fallo (puede exigir un objeto "
                            f"AeccPointExportOptions no soportado aqui, o el formato/ruta "
                            f"son invalidos): {exc}"
                        )
                    }
                return {"success": True, "ruta_archivo": ruta_archivo, "formato": formato}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="crear_puntos_cogo_multiples",
        description=(
            "Crea varios puntos COGO de una sola vez a partir de una lista de "
            "coordenadas [este, norte, elevacion]. Mas eficiente que llamar a "
            "`crear_punto_cogo` en bucle (una sola llamada COM en vez de una por punto). "
            "LECCION: `Document.Points.AddMultiple(cantidad, array_plano_xyz, 0)` "
            "confirmado en la guia oficial de desarrollo de Civil3D (Civil3D-DevGuide, "
            "'Using the Points Collection'); el array es plano (x1,y1,z1,x2,y2,z2,...), "
            "no anidado. El significado exacto del tercer parametro ('0' en el ejemplo "
            "oficial) no se explica en la documentacion; se usa el mismo valor literal "
            "que el ejemplo, sin inventar alternativas. Los puntos creados no permiten "
            "fijar numero/descripcion en la misma llamada (a diferencia de "
            "`crear_punto_cogo`); numeralos/describelos despues si lo necesitas."
        ),
    )
    async def crear_puntos_cogo_multiples(
        coordenadas: list[list[float]],
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        coordenadas : list[[este, norte, elevacion]]
            Lista de puntos a crear, cada uno como [este, norte, elevacion].
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                if not coordenadas:
                    return {"error": "coordenadas no puede estar vacio."}
                plano: list[float] = []
                for c in coordenadas:
                    if len(c) != 3:
                        return {"error": f"Cada punto debe tener 3 valores [este, norte, elevacion], recibido: {c}"}
                    plano.extend([float(c[0]), float(c[1]), float(c[2])])
                array_var = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, plano
                )
                try:
                    n_creados = client._doc.Points.AddMultiple(len(coordenadas), array_var, 0)
                except Exception as exc:
                    return {"error": f"AddMultiple fallo: {exc}"}
                return {"success": True, "solicitados": len(coordenadas), "creados": int(n_creados)}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="listar_grupos_puntos",
        description="Lista los grupos de puntos COGO del dibujo (Document.PointGroups).",
    )
    async def listar_grupos_puntos() -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                grupos = []
                for g in client._doc.PointGroups:
                    info = {"nombre": g.Name}
                    try:
                        info["total_puntos"] = g.Points.Count
                    except Exception:
                        pass
                    grupos.append(info)
                return {"total": len(grupos), "grupos": grupos}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_grupo_puntos",
        description=(
            "Crea un grupo de puntos, opcionalmente filtrado por numero de punto. "
            "LECCION: `Document.PointGroups.Add(nombre)` confirmado en la guia oficial de "
            "desarrollo de Civil3D (Civil3D-DevGuide, 'Creating Point Groups'). CORREGIDO "
            "26/07/2026: si filtra por numero, si es alcanzable via ActiveX legacy "
            "(`PointGroup.QueryBuilder.IncludeNumbers`, probado en vivo) - la version "
            "anterior de esta LECCION decia que la consulta era .NET-only, confundiendo "
            "este objeto (`AeccPointGroupQueryBuilder`) con `PointGroupQuery`/"
            "`StandardPointGroupQuery` de la API .NET moderna, que es distinto. "
            "filtro_numeros acepta el mismo formato que la UI: lista separada por comas "
            "y rangos con guion, ej '10-18' o '1,3,5-9'. Sin filtro_numeros, el grupo se "
            "crea vacio (comportamiento anterior)."
        ),
    )
    async def crear_grupo_puntos(nombre: str, filtro_numeros: str = "") -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre : str
            Nombre del nuevo grupo de puntos.
        filtro_numeros : str
            Opcional. Filtro de numeros de punto a incluir en el grupo, formato
            Civil3D nativo: lista separada por comas y/o rangos con guion
            (ej. '10-18' o '1,3,5-9'). Si se omite, el grupo se crea vacio.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                try:
                    grupo = client._doc.PointGroups.Add(nombre)
                except Exception as exc:
                    return {"error": f"No se pudo crear el grupo de puntos: {exc}"}
                if filtro_numeros:
                    try:
                        grupo.QueryBuilder.IncludeNumbers = filtro_numeros
                    except Exception as exc:
                        return {
                            "success": True,
                            "nombre": grupo.Name,
                            "aviso": f"Grupo creado pero el filtro fallo: {exc}",
                        }
                total_puntos = None
                try:
                    total_puntos = grupo.Points.Count
                except Exception:
                    pass
                return {
                    "success": True,
                    "nombre": grupo.Name,
                    "filtro_numeros": filtro_numeros or None,
                    "total_puntos": total_puntos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="eliminar_grupo_puntos",
        description="Borra un grupo de puntos por nombre exacto (no borra los puntos que contiene).",
    )
    async def eliminar_grupo_puntos(nombre: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                grupo = None
                for g in client._doc.PointGroups:
                    if g.Name == nombre:
                        grupo = g
                        break
                if grupo is None:
                    return {"error": f"Grupo de puntos '{nombre}' no encontrado."}
                grupo.Delete()
                return {"success": True, "nombre": nombre}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
