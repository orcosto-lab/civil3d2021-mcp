"""
tools_surfaces.py  -  Herramientas para superficies TIN de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError, iter_com_collection

log = logging.getLogger("civil3d_mcp.tools.surfaces")


def _buscar_superficie(client: Civil3DClient, nombre: str):
    """Busca una superficie por nombre exacto en client._doc.Surfaces. None si no existe."""
    for surf in iter_com_collection(client._doc.Surfaces):
        if surf.Name == nombre:
            return surf
    return None


def _buscar_grupo_puntos(client: Civil3DClient, nombre: str):
    """Busca un grupo de puntos por nombre exacto en client._doc.PointGroups. None si no existe."""
    for g in client._doc.PointGroups:
        if g.Name == nombre:
            return g
    return None


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="list_surfaces",
        description="Lista todas las superficies TIN del dibujo con nombre, descripcion y estadisticas.",
    )
    async def list_surfaces() -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                resultado = []
                for surf in iter_com_collection(client._doc.Surfaces):
                    info = {
                        "nombre": surf.Name,
                        "descripcion": surf.Description,
                        "tipo": surf.ObjectName,
                    }
                    try:
                        info["handle"] = surf.Handle
                    except Exception:
                        pass
                    try:
                        stats = surf.Statistics
                        info["elevacion_min"] = stats.MinimumElevation
                        info["elevacion_max"] = stats.MaximumElevation
                        info["num_puntos"] = stats.NumberOfPoints
                        info["num_triangulos"] = stats.NumberOfTriangles
                    except Exception:
                        pass
                    resultado.append(info)
                return {"total": len(resultado), "superficies": resultado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="elevacion_en_punto",
        description="Obtiene la elevacion de una superficie TIN en las coordenadas X,Y dadas.",
    )
    async def elevacion_en_punto(
        nombre_superficie: str,
        x: float,
        y: float,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_superficie : str
            Nombre exacto de la superficie (case-sensitive).
        x : float
            Coordenada Este.
        y : float
            Coordenada Norte.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                elev = surf.FindElevationAtXY(x, y)
                return {
                    "superficie": nombre_superficie,
                    "x": x,
                    "y": y,
                    "elevacion": elev,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="definicion_superficie",
        description=(
            "Lista los elementos que definen una superficie TIN: contornos (boundaries), "
            "lineas de rotura (breaklines), curvas de nivel importadas, archivos DEM, "
            "grupos de puntos y figuras/puntos de topografia (via Surface.DataDefinition). "
            "NO PROBADA: nombres de sub-colecciones tomados del proyecto civil3d_github "
            "(no oficiales, sin verificar contra la API COM real ni contra un dibujo con "
            "superficie definida por varias fuentes); cada sub-coleccion falla de forma "
            "independiente sin abortar el resto."
        ),
    )
    async def definicion_superficie(nombre_superficie: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                try:
                    defn = surf.DataDefinition
                except Exception as exc:
                    return {
                        "superficie": nombre_superficie,
                        "error": f"DataDefinition no disponible para este tipo de superficie: {exc}",
                    }
                colecciones = [
                    ("Boundaries", "contornos"),
                    ("Breaklines", "lineas_rotura"),
                    ("Contours", "curvas_nivel"),
                    ("DEMFiles", "archivos_dem"),
                    ("DrawingObjects", "objetos_dibujo"),
                    ("PointFiles", "archivos_puntos"),
                    ("PointGroups", "grupos_puntos"),
                    ("SurveyPoints", "puntos_topografia"),
                    ("SurveyFigures", "figuras_topografia"),
                ]
                definiciones: dict[str, Any] = {}
                for attr, clave in colecciones:
                    col = getattr(defn, attr, None)
                    if col is None:
                        definiciones[clave] = {"total": 0, "items": []}
                        continue
                    try:
                        items = []
                        for item in iter_com_collection(col):
                            item_info = {"nombre": str(getattr(item, "Name", repr(item)))}
                            for prop, clave_prop in (
                                ("Description", "descripcion"),
                                ("BreaklineType", "tipo_rotura"),
                                ("BoundaryType", "tipo_contorno"),
                                ("FileName", "archivo"),
                                ("StyleName", "estilo"),
                            ):
                                valor = getattr(item, prop, None)
                                if valor is not None:
                                    item_info[clave_prop] = str(valor)
                            items.append(item_info)
                        definiciones[clave] = {"total": len(items), "items": items}
                    except Exception as exc:
                        definiciones[clave] = {"error": str(exc)}
                return {"superficie": nombre_superficie, "definiciones": definiciones}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="verificar_superficie",
        description=(
            "Deteccion basica de anomalias/picos en una superficie TIN: muestrea una "
            "malla regular dentro de un bounding box (x_min,y_min,x_max,y_max) y, para "
            "cada punto interior, compara su elevacion con el promedio de sus 4 vecinos "
            "de malla (N/S/E/O); si la diferencia supera umbral_anomalia_m se marca como "
            "posible anomalia (punto de topografia erroneo, breakline mal definida, etc). "
            "No es un QC oficial de Civil 3D/sacred (que trabaja sobre los triangulos "
            "reales de la TIN): es una heuristica de malla regular, pensada para detectar "
            "picos/simas evidentes, no errores sutiles cerca de breaklines. "
            "LECCION: tope duro de 900 puntos de malla (nx*ny) - la malla se muestrea una "
            "sola vez y los vecinos se reutilizan de la misma malla (no hay llamadas COM "
            "adicionales por comparacion), pero aun asi 900 llamadas a FindElevationAtXY "
            "puede tardar segundos; ajusta resolucion_m al tamano real de la zona a revisar."
        ),
    )
    async def verificar_superficie(
        nombre_superficie: str,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        resolucion_m: float = 10.0,
        umbral_anomalia_m: float = 1.0,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                if resolucion_m <= 0:
                    return {"error": "resolucion_m debe ser positivo."}
                ancho = x_max - x_min
                alto = y_max - y_min
                if ancho <= 0 or alto <= 0:
                    return {"error": "El bounding box (x_min,y_min,x_max,y_max) es invalido."}

                nx = int(ancho // resolucion_m) + 1
                ny = int(alto // resolucion_m) + 1
                if nx * ny > 900:
                    return {
                        "error": (
                            f"La malla resultante ({nx * ny} puntos) supera el tope de 900. "
                            f"Sube resolucion_m o reduce el bounding box."
                        )
                    }
                if nx < 3 or ny < 3:
                    return {
                        "error": (
                            "El bounding box es demasiado pequeno para esta resolucion "
                            "(hacen falta al menos 3x3 puntos de malla)."
                        )
                    }

                grid: list[list[float | None]] = []
                for i in range(nx):
                    x = x_min + i * resolucion_m
                    fila = []
                    for j in range(ny):
                        y = y_min + j * resolucion_m
                        try:
                            fila.append(surf.FindElevationAtXY(x, y))
                        except Exception:
                            fila.append(None)
                    grid.append(fila)

                anomalias = []
                muestras_validas = 0
                for i in range(nx):
                    for j in range(ny):
                        if grid[i][j] is not None:
                            muestras_validas += 1

                for i in range(1, nx - 1):
                    for j in range(1, ny - 1):
                        z = grid[i][j]
                        if z is None:
                            continue
                        vecinos = [grid[i - 1][j], grid[i + 1][j], grid[i][j - 1], grid[i][j + 1]]
                        vecinos_validos = [v for v in vecinos if v is not None]
                        if len(vecinos_validos) < 2:
                            continue
                        promedio = sum(vecinos_validos) / len(vecinos_validos)
                        diferencia = z - promedio
                        if abs(diferencia) > umbral_anomalia_m:
                            anomalias.append({
                                "x": x_min + i * resolucion_m,
                                "y": y_min + j * resolucion_m,
                                "z": z,
                                "z_promedio_vecinos": promedio,
                                "diferencia_m": diferencia,
                            })

                return {
                    "superficie": nombre_superficie,
                    "resolucion_m": resolucion_m,
                    "umbral_anomalia_m": umbral_anomalia_m,
                    "puntos_malla": nx * ny,
                    "puntos_validos": muestras_validas,
                    "total_anomalias": len(anomalias),
                    "anomalias": anomalias,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_superficie",
        description=(
            "Crea una superficie TIN nueva, opcionalmente con puntos COGO ya asignados "
            "(via un grupo de puntos nuevo o uno ya existente). Geometria nueva en capa "
            "'IA' por defecto (convencion del proyecto). "
            "LECCION: `AeccXLand.AeccTinCreationData.<ver>` + `Surfaces.AddTinSurface` "
            "confirmados en vivo (26/07/2026) - la libreria es `AeccXLand`, NO "
            "`AeccXUiLand` (la del objeto Application/Document). Hay que rellenar TODAS "
            "las propiedades del objeto de creacion (Name/BaseLayer/Layer/Style/"
            "Description) antes de llamar Add, igual que con AeccTinVolumeCreationData. "
            "LECCION: filtro_numeros usa `PointGroup.QueryBuilder.IncludeNumbers` "
            "(ActiveX legacy, confirmado en vivo), formato Civil3D nativo: '10-18' o "
            "'1,3,5-9'. estilo debe ser un Surface Style YA EXISTENTE en el dibujo; si se "
            "omite se usa el primero disponible (`SurfaceStyles.Item(0)`), sin garantia "
            "de cual sea visualmente. Pasar filtro_numeros Y grupo_puntos_existente a la "
            "vez es un error (ambiguo)."
        ),
    )
    async def crear_superficie(
        nombre: str,
        filtro_numeros: str = "",
        grupo_puntos_existente: str = "",
        estilo: str = "",
        capa: str = "IA",
        descripcion: str = "",
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre : str
            Nombre de la nueva superficie TIN. Falla si ya existe una superficie con
            ese nombre.
        filtro_numeros : str
            Opcional. Crea un grupo de puntos NUEVO (nombre '{nombre}_puntos') filtrado
            por numero de punto Civil3D nativo (ej. '10-18' o '1,3,5-9') y lo asocia a
            la superficie. No usar junto con grupo_puntos_existente.
        grupo_puntos_existente : str
            Opcional. Nombre de un grupo de puntos YA EXISTENTE en el dibujo a asociar
            directamente a la superficie, en vez de crear uno nuevo. No usar junto con
            filtro_numeros.
        estilo : str
            Opcional. Nombre de un Surface Style ya existente en el dibujo. Si se omite,
            se usa el primero disponible (SurfaceStyles.Item(0)).
        capa : str
            Capa donde se crea la superficie. Por defecto 'IA' (convencion del proyecto
            para geometria nueva).
        descripcion : str
            Descripcion de la superficie.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                if client._acad is None:
                    raise Civil3DError("AutoCAD Application COM no disponible.")
                if filtro_numeros and grupo_puntos_existente:
                    return {
                        "error": "Pasa filtro_numeros O grupo_puntos_existente, no ambos."
                    }
                if _buscar_superficie(client, nombre) is not None:
                    return {"error": f"Ya existe una superficie llamada '{nombre}'."}

                grupo = None
                if grupo_puntos_existente:
                    grupo = _buscar_grupo_puntos(client, grupo_puntos_existente)
                    if grupo is None:
                        return {
                            "error": (
                                f"Grupo de puntos '{grupo_puntos_existente}' no encontrado."
                            )
                        }

                estilo_usado = estilo
                if not estilo_usado:
                    try:
                        estilo_usado = client._doc.SurfaceStyles.Item(0).Name
                    except Exception as exc:
                        return {"error": f"No se pudo obtener un SurfaceStyle por defecto: {exc}"}

                try:
                    tin_data = client._acad.GetInterfaceObject(
                        "AeccXLand.AeccTinCreationData.13.3"
                    )
                    tin_data.Name = nombre
                    tin_data.BaseLayer = capa
                    tin_data.Layer = capa
                    tin_data.Style = estilo_usado
                    tin_data.Description = descripcion
                    surf = client._doc.Surfaces.AddTinSurface(tin_data)
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo crear la superficie (revisa que '{estilo_usado}' "
                            f"exista como Surface Style en el dibujo): {exc}"
                        )
                    }

                if filtro_numeros:
                    nombre_grupo = f"{nombre}_puntos"
                    if _buscar_grupo_puntos(client, nombre_grupo) is not None:
                        return {
                            "success": True,
                            "nombre": surf.Name,
                            "aviso": (
                                f"Superficie creada, pero ya existe un grupo de puntos "
                                f"llamado '{nombre_grupo}' - no se le asignaron puntos."
                            ),
                        }
                    try:
                        grupo = client._doc.PointGroups.Add(nombre_grupo)
                        grupo.QueryBuilder.IncludeNumbers = filtro_numeros
                    except Exception as exc:
                        return {
                            "success": True,
                            "nombre": surf.Name,
                            "aviso": f"Superficie creada, pero el grupo de puntos fallo: {exc}",
                        }

                if grupo is not None:
                    try:
                        surf.PointGroups.Add(grupo)
                        surf.Update()
                    except Exception as exc:
                        return {
                            "success": True,
                            "nombre": surf.Name,
                            "aviso": f"Superficie creada, pero no se pudo asociar el grupo de puntos: {exc}",
                        }

                num_puntos = None
                try:
                    num_puntos = surf.Statistics.NumberOfPoints
                except Exception:
                    pass

                return {
                    "success": True,
                    "nombre": surf.Name,
                    "capa": capa,
                    "estilo": estilo_usado,
                    "grupo_puntos": grupo.Name if grupo is not None else None,
                    "num_puntos": num_puntos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
