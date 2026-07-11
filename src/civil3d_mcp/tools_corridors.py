"""
tools_corridors.py  -  Herramientas para corredores de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.corridors")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="list_corridors",
        description="Lista todos los corredores del dibujo con nombre y alineacion asociada.",
    )
    async def list_corridors() -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                try:
                    corridors = client._doc.Corridors
                except Exception:
                    return {"total": 0, "corredores": [], "nota": "Corredores no disponibles en esta version"}
                resultado = []
                for cor in corridors:
                    resultado.append({
                        "nombre": cor.Name,
                        "descripcion": cor.Description,
                    })
                return {"total": len(resultado), "corredores": resultado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
