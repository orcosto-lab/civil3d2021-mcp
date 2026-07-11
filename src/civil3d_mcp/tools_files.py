"""
tools_files.py  -  Gestion del archivo DWG (guardar, purgar, cambiar documento)
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.files")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="guardar_dibujo",
        description="Guarda el dibujo activo (equivalente a CTRL+S).",
    )
    async def guardar_dibujo() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                doc.Save()
                return {"success": True, "archivo": doc.FullName}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="guardar_como",
        description="Guarda el dibujo activo con un nombre y ruta nuevos.",
    )
    async def guardar_como(ruta: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                doc.SaveAs(ruta)
                return {"success": True, "ruta": ruta}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="purgar_dibujo",
        description="Purga el dibujo eliminando capas, bloques y estilos no utilizados (usa -PURGE para evitar dialogo).",
    )
    async def purgar_dibujo() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.SendCommand("-PURGE\nA\n*\nN\n")
                return {"success": True, "mensaje": "Purga ejecutada"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="activar_dibujo",
        description=(
            "Activa (hace current) un documento DWG abierto en Civil 3D por nombre parcial. "
            "Ejemplo: 'Drawing2' activa el dibujo cuyo nombre contiene ese texto. "
            "Devuelve lista de documentos abiertos si no se encuentra el nombre."
        ),
    )
    async def activar_dibujo(nombre: str) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre : str
            Parte del nombre del documento a activar (sin distinguir mayusculas).
        """
        try:
            def _run():
                acad = client._get_acad()
                docs = acad.Documents
                nombres = []
                for doc in docs:
                    nombres.append(doc.Name)
                    if nombre.lower() in doc.Name.lower():
                        doc.Activate()
                        return {"success": True, "dibujo_activado": doc.Name}
                return {
                    "error": f"No encontrado '{nombre}'",
                    "documentos_abiertos": nombres,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="listar_dibujos_abiertos",
        description="Lista todos los documentos DWG actualmente abiertos en Civil 3D.",
    )
    async def listar_dibujos_abiertos() -> dict[str, Any]:
        try:
            def _run():
                acad = client._get_acad()
                docs = []
                for doc in acad.Documents:
                    docs.append({
                        "nombre": doc.Name,
                        "ruta": doc.FullName,
                        "activo": doc.Name == acad.ActiveDocument.Name,
                    })
                return {"total": len(docs), "documentos": docs}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
