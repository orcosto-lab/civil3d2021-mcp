"""
tools_surfaces.py  -  Herramientas para superficies TIN de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.surfaces")


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
                surfaces = client._doc.Surfaces
                resultado = []
                for surf in surfaces:
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
                for surf in client._doc.Surfaces:
                    if surf.Name == nombre_superficie:
                        elev = surf.FindElevationAtXY(x, y)
                        return {
                            "superficie": nombre_superficie,
                            "x": x,
                            "y": y,
                            "elevacion": elev,
                        }
                return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
