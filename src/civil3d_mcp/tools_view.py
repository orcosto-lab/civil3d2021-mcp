"""
tools_view.py  -  Control de vistas y zoom en AutoCAD/Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.view")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="zoom_extension",
        description="Ajusta la vista para mostrar todos los objetos del dibujo (zoom extension).",
    )
    async def zoom_extension() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand("ZOOM\nE\n")
                return {"success": True, "mensaje": "Zoom extension ejecutado"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_todo",
        description="Zoom para mostrar todos los limites del dibujo (ZOOM A).",
    )
    async def zoom_todo() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand("ZOOM\nA\n")
                return {"success": True, "mensaje": "Zoom todo ejecutado"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_escala",
        description="Aplica un zoom por escala. Valores > 1 acercan, < 1 alejan. Ejemplo: 2 dobla el zoom.",
    )
    async def zoom_escala(escala: float) -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand(f"ZOOM\n{escala}X\n")
                return {"success": True, "escala": escala}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_previo",
        description="Vuelve a la vista anterior (equivalente a ZOOM P en AutoCAD).",
    )
    async def zoom_previo() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand("ZOOM\nP\n")
                return {"success": True, "mensaje": "Zoom previo ejecutado"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="vista_planta",
        description="Activa la vista en planta (vista superior, SCP mundo).",
    )
    async def vista_planta() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand("-VIEW\nTop\n\n")
                return {"success": True, "mensaje": "Vista planta activada"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="vista_isometrica_sw",
        description="Activa la vista isometrica SW (suroeste). Util para ver superficies 3D.",
    )
    async def vista_isometrica_sw() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand("-VIEW\nSW\n\n")
                return {"success": True, "mensaje": "Vista isometrica SW activada"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="regenerar_vista",
        description="Regenera la vista del dibujo (equivalente a REGEN). Util para actualizar la pantalla.",
    )
    async def regenerar_vista() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.Regen(1)
                return {"success": True, "mensaje": "Vista regenerada"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
