"""
tools_blocks.py  -  Herramientas para bloques en AutoCAD/Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.blocks")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="listar_bloques",
        description="Lista todas las definiciones de bloque en el dibujo.",
    )
    async def listar_bloques() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                bloques = []
                for bloque in doc.Blocks:
                    if bloque.Name.startswith("*"):
                        continue  # Bloques internos (*Model_Space, *Paper_Space)
                    bloques.append({"nombre": bloque.Name, "num_objetos": bloque.Count})
                return {"total": len(bloques), "bloques": bloques}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="insertar_bloque",
        description="Inserta una referencia de bloque en el dibujo en las coordenadas indicadas.",
    )
    async def insertar_bloque(
        nombre: str,
        x: float,
        y: float,
        z: float = 0.0,
        escala: float = 1.0,
        rotacion_grados: float = 0.0,
        capa: str = "0",
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre : str
            Nombre del bloque (debe existir en el dibujo).
        x, y, z : float
            Punto de insercion.
        escala : float
            Factor de escala uniforme.
        rotacion_grados : float
            Rotacion en grados sexagesimales.
        capa : str
            Capa destino.
        """
        try:
            def _run():
                import math
                doc = client.active_doc
                ms = doc.ModelSpace
                pt = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [x, y, z],
                )
                ref = ms.InsertBlock(pt, nombre, escala, escala, escala,
                                     math.radians(rotacion_grados))
                ref.Layer = capa
                return {
                    "success": True,
                    "handle": ref.Handle,
                    "bloque": nombre,
                    "capa": capa,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
