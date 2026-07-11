"""
tools_alignments.py  -  Herramientas para alineaciones de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.alignments")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="list_alignments",
        description="Lista todas las alineaciones del dibujo con nombre, longitud y PK inicial/final.",
    )
    async def list_alignments() -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alignments = client._doc.AlignmentsSiteless
                resultado = []
                for alig in alignments:
                    info = {
                        "nombre": alig.Name,
                        "descripcion": alig.Description,
                        "longitud": alig.Length,
                        "pk_inicio": alig.StartingStation,
                        "pk_fin": alig.EndingStation,
                    }
                    resultado.append(info)
                return {"total": len(resultado), "alineaciones": resultado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="coordenadas_en_pk",
        description="Obtiene las coordenadas X,Y de una alineacion en un PK (estacionamiento) dado.",
    )
    async def coordenadas_en_pk(
        nombre_alineacion: str,
        pk: float,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        pk : float
            Estacionamiento (PK) en metros.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                for alig in client._doc.AlignmentsSiteless:
                    if alig.Name == nombre_alineacion:
                        x = alig.GetXAtStation(pk)
                        y = alig.GetYAtStation(pk)
                        return {
                            "alineacion": nombre_alineacion,
                            "pk": pk,
                            "x": x,
                            "y": y,
                        }
                return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
