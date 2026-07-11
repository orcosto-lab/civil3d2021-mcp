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
        description="Elimina todas las capas que no tienen objetos asignados (excepto la capa 0 y la capa activa).",
    )
    async def eliminar_capas_vacias() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                ms = doc.ModelSpace
                capas_usadas = {"0"}
                capas_usadas.add(doc.ActiveLayer.Name.lower())
                for obj in ms:
                    capas_usadas.add(obj.Layer.lower())
                eliminadas = []
                for capa in list(doc.Layers):
                    if capa.Name.lower() not in capas_usadas:
                        try:
                            capa.Delete()
                            eliminadas.append(capa.Name)
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
