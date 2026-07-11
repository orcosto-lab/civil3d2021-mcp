"""
tools_cogo.py  -  Herramientas para puntos COGO de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.cogo")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="listar_puntos_cogo",
        description="Lista los puntos COGO del dibujo (maximo 200). Devuelve numero, descripcion y coordenadas.",
    )
    async def listar_puntos_cogo() -> dict[str, Any]:
        try:
            def _run():
                points_col = client._get_cogo_collection()
                puntos = []
                if points_col is not None:
                    for pt in points_col:
                        try:
                            puntos.append({
                                "numero": pt.Number,
                                "descripcion": pt.RawDescription,
                                "norte": pt.Northing,
                                "este": pt.Easting,
                                "elevacion": pt.Elevation,
                            })
                        except Exception:
                            pass
                        if len(puntos) >= 200:
                            break
                else:
                    # Fallback: escanear ModelSpace
                    ms = client.model_space
                    for obj in ms:
                        if "CogoPoint" in obj.ObjectName or "AeccDb" in obj.ObjectName:
                            try:
                                puntos.append({
                                    "numero": obj.Number,
                                    "descripcion": obj.RawDescription,
                                    "norte": obj.Northing,
                                    "este": obj.Easting,
                                    "elevacion": obj.Elevation,
                                })
                            except Exception:
                                pass
                            if len(puntos) >= 200:
                                break
                return {"total": len(puntos), "puntos": puntos}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_punto_cogo",
        description="Crea un punto COGO en el dibujo con numero, descripcion y coordenadas.",
    )
    async def crear_punto_cogo(
        numero: int,
        norte: float,
        este: float,
        elevacion: float = 0.0,
        descripcion: str = "",
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        numero : int
            Numero del punto COGO.
        norte : float
            Coordenada Norte (Y).
        este : float
            Coordenada Este (X).
        elevacion : float
            Elevacion Z (por defecto 0).
        descripcion : str
            Descripcion raw del punto.
        """
        try:
            def _run():
                points_col = client._get_cogo_collection()
                if points_col is None:
                    raise Civil3DError("Civil 3D no disponible para crear puntos COGO.")
                # pts.Add requiere VARIANT array [Este, Norte, Elevacion] - orden critico
                coords = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [float(este), float(norte), float(elevacion)]
                )
                pt = points_col.Add(coords)
                if descripcion:
                    pt.RawDescription = descripcion
                pt.Number = numero
                return {
                    "success": True,
                    "numero": pt.Number,
                    "norte": pt.Northing,
                    "este": pt.Easting,
                    "elevacion": pt.Elevation,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
