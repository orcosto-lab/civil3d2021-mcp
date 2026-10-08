"""
tools_layers.py  -  Gestion de capas en AutoCAD/Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.layers")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="crear_capa",
        description="Crea una nueva capa en el dibujo. Si ya existe, no hace nada.",
    )
    async def crear_capa(nombre: str, color: int = 7) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                for capa in doc.Layers:
                    if capa.Name.lower() == nombre.lower():
                        return {"success": True, "creada": False, "mensaje": f"Capa '{nombre}' ya existe"}
                capa = doc.Layers.Add(nombre)
                capa.color = color
                return {"success": True, "creada": True, "nombre": capa.Name, "color": color}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="activar_capa",
        description="Activa una capa (la hace la capa actual del dibujo).",
    )
    async def activar_capa(nombre: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                doc.ActiveLayer = doc.Layers.Item(nombre)
                return {"success": True, "capa_activa": nombre}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="congelar_capa",
        description="Congela o descongela una capa.",
    )
    async def congelar_capa(nombre: str, congelar: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                capa.Freeze = congelar
                accion = "congelada" if congelar else "descongelada"
                return {"success": True, "capa": nombre, "estado": accion}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="bloquear_capa",
        description="Bloquea o desbloquea una capa.",
    )
    async def bloquear_capa(nombre: str, bloquear: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                capa.Lock = bloquear
                accion = "bloqueada" if bloquear else "desbloqueada"
                return {"success": True, "capa": nombre, "estado": accion}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="eliminar_capa",
        description="Elimina una capa vacia del dibujo. Falla si la capa tiene objetos.",
    )
    async def eliminar_capa(nombre: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                capa.Delete()
                return {"success": True, "eliminada": nombre}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="eliminar_capas_vacias",
        description=(
            "Elimina todas las capas que no tienen objetos asignados (excepto la capa 0 y "
            "la capa activa). Usa la propiedad nativa Layer.Used (COM) en vez de escanear "
            "ModelSpace a mano: mas eficiente y detecta uso en TODO el dibujo (incluye "
            "Paper Space y definiciones de bloque, no solo ModelSpace)."
        ),
    )
    async def eliminar_capas_vacias() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                activa = doc.ActiveLayer.Name.lower()
                eliminadas = []
                for capa in list(doc.Layers):
                    nombre_lower = capa.Name.lower()
                    if nombre_lower == "0" or nombre_lower == activa:
                        continue
                    if not capa.Used:
                        try:
                            nombre_capa = capa.Name
                            capa.Delete()
                            eliminadas.append(nombre_capa)
                        except Exception:
                            pass
                return {"eliminadas": eliminadas, "total": len(eliminadas)}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="cambiar_color_capa",
        description="Cambia el color ACI de una capa (1=rojo, 2=amarillo, 3=verde, 4=cyan, 5=azul, 6=magenta, 7=blanco).",
    )
    async def cambiar_color_capa(nombre: str, color: int) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                capa.color = color
                return {"success": True, "capa": nombre, "color": color}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="activar_visibilidad_capa",
        description=(
            "Enciende o apaga la visibilidad de una capa (propiedad LayerOn). Distinto de "
            "congelar_capa (Freeze, tambien excluye la capa del calculo de zoom/regen) y de "
            "bloquear_capa (Lock, impide edicion pero mantiene visible). Una capa apagada "
            "sigue existiendo y sus objetos siguen contandose en listar_objetos/contar_objetos."
        ),
    )
    async def activar_visibilidad_capa(nombre: str, encender: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                capa.LayerOn = encender
                estado = "encendida" if encender else "apagada"
                return {"success": True, "capa": nombre, "estado": estado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="imprimir_capa",
        description=(
            "Activa o desactiva la propiedad Plottable de una capa: si se incluye al "
            "plotear/imprimir, independientemente de su visibilidad en pantalla (LayerOn) "
            "o de si esta congelada/bloqueada. NO PROBADA aun."
        ),
    )
    async def imprimir_capa(nombre: str, imprimir: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                capa.Plottable = imprimir
                estado = "imprimible" if imprimir else "no imprimible"
                return {"success": True, "capa": nombre, "estado": estado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="linea_capa",
        description=(
            "Cambia el tipo de linea (Linetype) y/o el grosor (Lineweight, en centesimas "
            "de mm segun el enum AcLineWeight: 0,5,9,13,15,18,20,25,30,35,40,50,53,60,70,80,90,"
            "100,106,120,140,158,200,211; -1=ByBlock, -2=ByLayer, -3=Default) de una capa. "
            "Al menos uno de los dos parametros debe indicarse. Si el tipo de linea no esta "
            "cargado en el dibujo, intenta cargarlo desde acad.lin antes de asignarlo. "
            "NO PROBADA aun."
        ),
    )
    async def linea_capa(
        nombre: str,
        linetype: str | None = None,
        lineweight: int | None = None,
    ) -> dict[str, Any]:
        try:
            def _run():
                if linetype is None and lineweight is None:
                    return {"error": "Debe indicarse linetype y/o lineweight"}
                doc = client.active_doc
                capa = doc.Layers.Item(nombre)
                resultado: dict[str, Any] = {"success": True, "capa": nombre}
                if linetype is not None:
                    encontrado = any(
                        lt.Name.lower() == linetype.lower() for lt in doc.Linetypes
                    )
                    if not encontrado:
                        try:
                            doc.Linetypes.Load(linetype, "acad.lin")
                        except Exception as e:
                            return {"error": f"No se pudo cargar el tipo de linea '{linetype}': {e}"}
                    capa.Linetype = linetype
                    resultado["linetype"] = linetype
                if lineweight is not None:
                    capa.Lineweight = lineweight
                    resultado["lineweight"] = lineweight
                return resultado
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="renombrar_capa",
        description=(
            "Renombra una capa existente (propiedad Name via COM directo, sin SendCommand). "
            "No permite renombrar la capa '0' ni la capa Defpoints. Si el nombre nuevo ya "
            "existe, devuelve error sin modificar nada (AutoCAD no permite nombres duplicados)."
        ),
    )
    async def renombrar_capa(nombre_actual: str, nombre_nuevo: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                if nombre_actual.lower() in ("0", "defpoints"):
                    return {"error": f"No se permite renombrar la capa protegida '{nombre_actual}'"}
                for capa in doc.Layers:
                    if capa.Name.lower() == nombre_nuevo.lower():
                        return {"error": f"Ya existe una capa llamada '{nombre_nuevo}'"}
                capa = doc.Layers.Item(nombre_actual)
                capa.Name = nombre_nuevo
                return {"success": True, "nombre_anterior": nombre_actual, "nombre_nuevo": capa.Name}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="get_geometria_handles",
        description=(
            "Devuelve la geometria real (coordenadas UTM) de objetos AutoCAD dado sus handles. "
            "Soporta: AcDbLine (inicio/fin), AcDbPolyline/AcDb2dPolyline (vertices via Coordinates), "
            "AcDb3dPolyline, AcDbBlockReference (punto de insercion). Maximo 50 handles por llamada."
        ),
    )
    async def get_geometria_handles(handles: list[str]) -> dict[str, Any]:
        """
        Parameters
        ----------
        handles : list[str]
            Lista de handles AutoCAD (hexadecimal, obtenidos de listar_objetos).
        """
        try:
            def _run():
                doc = client.active_doc
                resultados = []
                for h in handles[:50]:
                    try:
                        obj = doc.HandleToObject(h)
                        tipo = obj.ObjectName

                        if tipo == "AcDbLine":
                            sp = obj.StartPoint
                            ep = obj.EndPoint
                            resultados.append({
                                "tipo": "Linea",
                                "handle": h,
                                "inicio": [round(sp[0], 4), round(sp[1], 4), round(sp[2], 4)],
                                "fin":    [round(ep[0], 4), round(ep[1], 4), round(ep[2], 4)],
                            })

                        elif tipo in ("AcDbPolyline", "AcDb2dPolyline"):
                            # LwPolyline: Coordinates es array plano [x1,y1,x2,y2,...]
                            coords = list(obj.Coordinates)
                            elev = 0.0
                            try:
                                elev = float(obj.Elevation)
                            except Exception:
                                pass
                            n = len(coords) // 2
                            verts = []
                            for i in range(n):
                                verts.append([round(coords[i*2], 4), round(coords[i*2+1], 4), round(elev, 4)])
                            resultados.append({
                                "tipo": "Polilinea",
                                "handle": h,
                                "cerrada": bool(obj.Closed),
                                "elevacion": round(elev, 4),
                                "vertices": verts,
                            })

                        elif tipo == "AcDb3dPolyline":
                            coords = list(obj.Coordinates)
                            verts = []
                            for i in range(len(coords) // 3):
                                verts.append([
                                    round(coords[i*3],   4),
                                    round(coords[i*3+1], 4),
                                    round(coords[i*3+2], 4),
                                ])
                            resultados.append({
                                "tipo": "Polilinea3D",
                                "handle": h,
                                "vertices": verts,
                            })

                        elif tipo == "AcDbBlockReference":
                            ip = obj.InsertionPoint
                            resultados.append({
                                "tipo": "Bloque",
                                "handle": h,
                                "nombre_bloque": obj.Name,
                                "insercion": [round(ip[0], 4), round(ip[1], 4), round(ip[2], 4)],
                            })

                        else:
                            # Intento generico via Coordinates o StartPoint/EndPoint
                            try:
                                coords = list(obj.Coordinates)
                                resultados.append({
                                    "tipo": tipo,
                                    "handle": h,
                                    "coordinates_raw": [round(c, 4) for c in coords[:30]],
                                })
                            except Exception:
                                resultados.append({
                                    "tipo": tipo,
                                    "handle": h,
                                    "nota": "tipo no soportado",
                                })

                    except Exception as e:
                        resultados.append({"handle": h, "error": str(e)})

                return {"total": len(resultados), "objetos": resultados}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="auditar_capas",
        description=(
            "Audita las capas del dibujo contra un estandar simple que TU defines: patron "
            "de nombre (regex opcional), lista de colores ACI permitidos (opcional) y lista "
            "de lineweights permitidos en centesimas de mm (opcional, ver enum AcLineWeight "
            "en `linea_capa`). No hay ninguna tabla de estandares de Autodesk/normativa "
            "hardcodeada: cada oficina/proyecto tiene su propio convenio de capas, asi que "
            "tu aportas las reglas. Protege siempre '0' y 'Defpoints' (nunca se marcan como "
            "incumplimiento). Solo lectura, no modifica nada (ver `corregir_capas`)."
        ),
    )
    async def auditar_capas(
        patron_nombre: str | None = None,
        colores_permitidos: list[int] | None = None,
        lineweights_permitidos: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        patron_nombre : str, opcional
            Regex que debe cumplir el nombre de la capa (ej. r"^\\d{2}-.+" para "01-Viales").
        colores_permitidos : list[int], opcional
            Lista de codigos de color ACI permitidos (1-255).
        lineweights_permitidos : list[int], opcional
            Lista de valores Lineweight permitidos (ver `linea_capa` para el enum).
        """
        try:
            def _run():
                import re
                regex = re.compile(patron_nombre) if patron_nombre else None
                doc = client.active_doc
                incumplimientos: list[dict[str, Any]] = []
                total = 0
                for capa in doc.Layers:
                    nombre = capa.Name
                    if nombre.lower() in ("0", "defpoints"):
                        continue
                    total += 1
                    problemas = []
                    if regex is not None and not regex.match(nombre):
                        problemas.append("nombre no cumple el patron")
                    try:
                        color = capa.color
                        if colores_permitidos is not None and color not in colores_permitidos:
                            problemas.append(f"color {color} no permitido")
                    except Exception:
                        pass
                    try:
                        lw = capa.Lineweight
                        if lineweights_permitidos is not None and lw not in lineweights_permitidos:
                            problemas.append(f"lineweight {lw} no permitido")
                    except Exception:
                        pass
                    if problemas:
                        incumplimientos.append({"capa": nombre, "problemas": problemas})
                return {
                    "total_capas_auditadas": total,
                    "incumplimientos": incumplimientos,
                    "total_incumplimientos": len(incumplimientos),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="corregir_capas",
        description=(
            "Aplica correcciones a las capas que incumplen el estandar (ver `auditar_capas`): "
            "puede renombrar (via mapa nombre_actual->nombre_nuevo), recolorear o cambiar el "
            "lineweight de las capas indicadas. Protege siempre '0' y 'Defpoints'. Cada capa "
            "se procesa de forma independiente: si una falla, se registra el error y se sigue "
            "con las demas (no aborta todo el lote)."
        ),
    )
    async def corregir_capas(
        renombrar: dict[str, str] | None = None,
        color: dict[str, int] | None = None,
        lineweight: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        renombrar : dict[str, str], opcional
            Mapa {nombre_actual: nombre_nuevo}.
        color : dict[str, int], opcional
            Mapa {nombre_capa: codigo_aci}.
        lineweight : dict[str, int], opcional
            Mapa {nombre_capa: valor_lineweight}.
        """
        try:
            def _run():
                doc = client.active_doc
                capas = doc.Layers
                resultados: list[dict[str, Any]] = []
                protegidas = ("0", "defpoints")

                for actual, nuevo in (renombrar or {}).items():
                    if actual.lower() in protegidas:
                        resultados.append({"capa": actual, "accion": "renombrar", "error": "capa protegida"})
                        continue
                    try:
                        capa = capas.Item(actual)
                        capa.Name = nuevo
                        resultados.append({"capa": actual, "accion": "renombrar", "ok": True, "nuevo_nombre": nuevo})
                    except Exception as exc:
                        resultados.append({"capa": actual, "accion": "renombrar", "error": str(exc)})

                for nombre, codigo in (color or {}).items():
                    if nombre.lower() in protegidas:
                        resultados.append({"capa": nombre, "accion": "color", "error": "capa protegida"})
                        continue
                    try:
                        capa = capas.Item(nombre)
                        capa.color = codigo
                        resultados.append({"capa": nombre, "accion": "color", "ok": True, "nuevo_color": codigo})
                    except Exception as exc:
                        resultados.append({"capa": nombre, "accion": "color", "error": str(exc)})

                for nombre, valor in (lineweight or {}).items():
                    if nombre.lower() in protegidas:
                        resultados.append({"capa": nombre, "accion": "lineweight", "error": "capa protegida"})
                        continue
                    try:
                        capa = capas.Item(nombre)
                        capa.Lineweight = valor
                        resultados.append({"capa": nombre, "accion": "lineweight", "ok": True, "nuevo_valor": valor})
                    except Exception as exc:
                        resultados.append({"capa": nombre, "accion": "lineweight", "error": str(exc)})

                return {"resultados": resultados, "total": len(resultados)}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
