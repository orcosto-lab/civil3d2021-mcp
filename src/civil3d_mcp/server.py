"""
server.py  -  Punto de entrada del servidor MCP para Civil 3D
Arquitectura: fastmcp + COM (pywin32)
Requiere: Civil 3D abierto con un dibujo activo antes de iniciar Claude Desktop
"""
from __future__ import annotations
import asyncio
import logging
import concurrent.futures
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient
from . import (
    tools_drawing,
    tools_cogo,
    tools_lines,
    tools_surfaces,
    tools_alignments,
    tools_corridors,
    tools_layers,
    tools_blocks,
    tools_view,
    tools_create,
    tools_files,
    tools_script,
    tools_mesh,
    tools_geometria,
    tools_cotas,
    tools_cache,
    tools_textos,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("civil3d_mcp")

mcp = FastMCP("civil3d-mcp")
client = Civil3DClient()
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


async def run_com(fn):
    """Ejecuta una funcion COM en el hilo dedicado (COM STA)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn)


# Registrar todos los modulos de herramientas
tools_drawing.register(mcp, client, run_com)
tools_cogo.register(mcp, client, run_com)
tools_lines.register(mcp, client, run_com)
tools_surfaces.register(mcp, client, run_com)
tools_alignments.register(mcp, client, run_com)
tools_corridors.register(mcp, client, run_com)
tools_layers.register(mcp, client, run_com)
tools_blocks.register(mcp, client, run_com)
tools_view.register(mcp, client, run_com)
tools_create.register(mcp, client, run_com)
tools_files.register(mcp, client, run_com)
tools_script.register(mcp, client, run_com)
tools_mesh.register(mcp, client, run_com)
tools_geometria.register(mcp, client, run_com)
tools_cotas.register(mcp, client, run_com)
tools_cache.register(mcp, client, run_com)
tools_textos.register(mcp, client, run_com)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
