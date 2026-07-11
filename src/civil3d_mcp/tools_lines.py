"""
tools_lines.py  -  Crear lineas y polilineas en AutoCAD/Civil 3D
Usa SendCommand en lugar de ms.AddLine/AddLightWeightPolyline para evitar
bloqueos COM con VARIANTs en el STA de AutoCAD.
"""
from __future__ import annotations
import logging
import time
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.lines")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="crear_linea",
        description=(
            "Crea una linea 3D entre dos puntos. "
            "Coordenadas en el SRC del dibujo (UTM o locales)."
        ),
    )
    async def crear_linea(
        x1: float, y1: float, z1: float,
        x2: float, y2: float, z2: float,
        capa: str = "0",
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                # Usar SendCommand para evitar bloqueo COM con VARIANT arrays
                cmd = (
                    f"_CLAYER\n{capa}\n"
                    f"_LINE\n{x1},{y1},{z1}\n{x2},{y2},{z2}\n\n"
                )
                doc.SendCommand(cmd)
                time.sleep(0.3)
                return {"success": True, "capa": capa,
                        "p1": [x1, y1, z1], "p2": [x2, y2, z2]}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_polilinea",
        description=(
            "Crea una polilinea 2D a partir de una lista de puntos [x1,y1, x2,y2, ...]. "
            "Para polilineas 3D usar acad_create_3dpolyline de civil3d-sacred."
        ),
    )
    async def crear_polilinea(
        puntos: list[float],
        capa: str = "0",
        cerrada: bool = False,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        puntos : list[float]
            Lista plana: [x1, y1, x2, y2, ...]. Minimo 4 valores (2 puntos).
        capa : str
            Capa destino.
        cerrada : bool
            Si True, cierra la polilinea.
        """
        try:
            def _run():
                if len(puntos) < 4 or len(puntos) % 2 != 0:
                    return {"error": "Minimo 2 puntos (4 valores x,y)"}
                doc = client.active_doc
                cmd = f"CLAYER\n{capa}\nPLINE\n"
                for i in range(0, len(puntos), 2):
                    cmd += f"{puntos[i]},{puntos[i+1]}\n"
                cmd += "C\n" if cerrada else "\n"
                doc.SendCommand(cmd)
                time.sleep(0.3)
                return {
                    "success": True,
                    "capa": capa,
                    "cerrada": cerrada,
                    "num_vertices": len(puntos) // 2,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
