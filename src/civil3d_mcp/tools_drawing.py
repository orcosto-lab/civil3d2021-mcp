"""
tools_drawing.py  -  Informacion general del dibujo activo
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError, con_reintentos

log = logging.getLogger("civil3d_mcp.tools.drawing")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="info_dibujo",
        description="Devuelve informacion basica del dibujo activo: nombre, ruta, unidades y version.",
    )
    async def info_dibujo() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                info = {}
                for attr, key in [("Name", "nombre"), ("FullName", "ruta"), ("Modified", "modificado")]:
                    try:
                        info[key] = getattr(doc, attr)
                    except Exception:
                        info[key] = None
                return info
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="listar_capas",
        description="Lista todas las capas del dibujo con su estado (activa, congelada, bloqueada).",
    )
    async def listar_capas() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                capas = []
                for capa in doc.Layers:
                    c = {"nombre": capa.Name}
                    for attr, key in [("LayerOn", "activa"), ("Freeze", "congelada"), ("Lock", "bloqueada"), ("color", "color")]:
                        try:
                            c[key] = getattr(capa, attr)
                        except Exception:
                            c[key] = None
                    capas.append(c)
                return {"total": len(capas), "capas": capas}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="contar_objetos",
        description=(
            "Cuenta los objetos en ModelSpace, opcionalmente filtrados por capa. "
            "LECCION: itera todo ModelSpace en una sola llamada (con o sin filtro "
            "de capa da igual, el filtro no reduce el numero de idas y vueltas "
            "COM); envuelta con reintento automatico ante RPC_E_CALL_REJECTED "
            "(contencion COM transitoria de Civil 3D, no un dialogo colgado -- "
            "ver con_reintentos en client.py)."
        ),
    )
    async def contar_objetos(capa: str = "") -> dict[str, Any]:
        try:
            def _contar():
                ms = client.model_space
                total = 0
                por_tipo: dict[str, int] = {}
                for obj in ms:
                    try:
                        if capa and obj.Layer.lower() != capa.lower():
                            continue
                        total += 1
                        tipo = obj.ObjectName
                        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
                    except Exception:
                        pass
                return {"total": total, "por_tipo": por_tipo, "filtro_capa": capa or "ninguno"}
            def _run():
                return con_reintentos(_contar)
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="listar_objetos",
        description=(
            "Lista objetos de ModelSpace en una capa especifica (maximo 100). "
            "LECCION: NO expone la geometria de vertices de polilineas - para obtener "
            "coordenadas reales usar get_geometria_handles con los handles devueltos. "
            "LECCION: itera todo ModelSpace en una sola llamada; envuelta con "
            "reintento automatico ante RPC_E_CALL_REJECTED (contencion COM "
            "transitoria de Civil 3D, no un dialogo colgado -- ver con_reintentos "
            "en client.py)."
        ),
    )
    async def listar_objetos(capa: str) -> dict[str, Any]:
        try:
            def _listar():
                ms = client.model_space
                objetos = []
                for obj in ms:
                    try:
                        if obj.Layer.lower() != capa.lower():
                            continue
                        info = {"tipo": obj.ObjectName, "handle": obj.Handle, "capa": obj.Layer}
                        try:
                            info["punto_insercion"] = list(obj.InsertionPoint)
                        except Exception:
                            pass
                        objetos.append(info)
                        if len(objetos) >= 100:
                            break
                    except Exception:
                        pass
                return {"total": len(objetos), "objetos": objetos}
            def _run():
                return con_reintentos(_listar)
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
