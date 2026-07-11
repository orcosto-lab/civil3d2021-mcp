"""
tools_create.py  -  Creacion de entidades y manipulacion de objetos
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.create")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="borrar_objeto",
        description="Borra un objeto del dibujo identificado por su handle.",
    )
    async def borrar_objeto(
        handle: str,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                obj = doc.HandleToObject(handle)
                obj.Delete()
                return {"success": True, "handle": handle}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_circulo",
        description="Crea un circulo en el plano XY centrado en (x, y, z) con el radio indicado.",
    )
    async def crear_circulo(
        x: float,
        y: float,
        z: float,
        radio: float,
        capa: str = "0",
    ) -> dict[str, Any]:
        try:
            def _run():
                ms = client.model_space
                centro = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z]
                )
                obj = ms.AddCircle(centro, radio)
                obj.Layer = capa
                return {
                    "success": True,
                    "handle": obj.Handle,
                    "centro": [x, y, z],
                    "radio": radio,
                    "capa": capa,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_texto",
        description="Inserta un texto de una linea en el dibujo en las coordenadas indicadas.",
    )
    async def crear_texto(
        texto: str,
        x: float,
        y: float,
        z: float = 0.0,
        altura: float = 1.0,
        capa: str = "0",
    ) -> dict[str, Any]:
        try:
            def _run():
                ms = client.model_space
                pt = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [x, y, z],
                )
                obj = ms.AddText(texto, pt, altura)
                obj.Layer = capa
                return {
                    "success": True,
                    "handle": obj.Handle,
                    "texto": texto,
                    "capa": capa,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="mover_a_capa",
        description=(
            "Mueve todos los objetos de una capa origen a una capa destino. "
            "Crea la capa destino si no existe."
        ),
    )
    async def mover_a_capa(capa_origen: str, capa_destino: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                ms = doc.ModelSpace
                nombres = [c.Name.lower() for c in doc.Layers]
                if capa_destino.lower() not in nombres:
                    doc.Layers.Add(capa_destino)
                movidos = 0
                for obj in ms:
                    if obj.Layer.lower() == capa_origen.lower():
                        obj.Layer = capa_destino
                        movidos += 1
                return {
                    "success": True,
                    "origen": capa_origen,
                    "destino": capa_destino,
                    "objetos_movidos": movidos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="cambiar_capa_objetos",
        description="Cambia la capa de uno o varios objetos identificados por sus handles.",
    )
    async def cambiar_capa_objetos(
        handles: list[str],
        capa_destino: str,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                # Crear capa destino si no existe
                nombres = [c.Name.lower() for c in doc.Layers]
                if capa_destino.lower() not in nombres:
                    doc.Layers.Add(capa_destino)
                movidos = []
                errores = []
                for handle in handles:
                    try:
                        obj = doc.HandleToObject(handle)
                        obj.Layer = capa_destino
                        movidos.append(handle)
                    except Exception as e:
                        errores.append({"handle": handle, "error": str(e)})
                return {
                    "success": True,
                    "movidos": movidos,
                    "capa_destino": capa_destino,
                    "errores": errores,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="copiar_objeto",
        description="Copia un objeto (por handle) desplazado por dx, dy, dz.",
    )
    async def copiar_objeto(
        handle: str,
        dx: float,
        dy: float,
        dz: float = 0.0,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                obj = doc.HandleToObject(handle)
                pt_base = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0, 0.0, 0.0]
                )
                pt_dest = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [dx, dy, dz]
                )
                copia = obj.Copy()
                copia.Move(pt_base, pt_dest)
                return {
                    "success": True,
                    "handle_original": handle,
                    "handle_copia": copia.Handle,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
