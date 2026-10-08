"""
tools_view.py  -  Control de vistas y zoom en AutoCAD/Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import pythoncom
from win32com.client import VARIANT
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.view")


def _punto(x: float, y: float, z: float = 0.0) -> VARIANT:
    """Punto 3D como VARIANT para metodos COM de zoom."""
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z])


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="zoom_extension",
        description=(
            "Ajusta la vista a la extension de los objetos del dibujo (ZoomExtents COM "
            "nativo, sin SendCommand — no necesita verificacion por log). Con el dibujo "
            "vacio muestra los limites."
        ),
    )
    async def zoom_extension() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.Application.ZoomExtents()
                return {"success": True, "mensaje": "Zoom extension ejecutado"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom",
        description=(
            "Zoom Todo (ZoomAll COM nativo, sin SendCommand). Muestra los limites del "
            "dibujo o la extension de los objetos, lo que sea mayor. LECCION: en vistas "
            "3D es identico a zoom_extension; en planta 2D con geometria dentro de "
            "limites encuadra los limites (rectangulo de plantilla), no los objetos — "
            "para cenir a los objetos usar zoom_extension."
        ),
    )
    async def zoom() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.Application.ZoomAll()
                return {"success": True, "mensaje": "Zoom todo (limites) ejecutado"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_escala",
        description=(
            "Aplica un zoom por factor de escala relativo a la vista actual (ZoomScaled "
            "COM nativo, sin SendCommand). Valores > 1 acercan, < 1 alejan. Ejemplo: 2 "
            "dobla el zoom."
        ),
    )
    async def zoom_escala(escala: float) -> dict[str, Any]:
        try:
            def _run():
                # 1 = acZoomScaledRelative (relativo a la vista actual, como nX)
                client.active_doc.Application.ZoomScaled(escala, 1)
                return {"success": True, "escala": escala}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_previo",
        description=(
            "Vuelve a la vista anterior (ZoomPrevious COM nativo, sin SendCommand). "
            "Solo restaura la inmediatamente anterior."
        ),
    )
    async def zoom_previo() -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.Application.ZoomPrevious()
                return {"success": True, "mensaje": "Zoom previo ejecutado"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_ventana",
        description=(
            "Zoom a una ventana rectangular definida por dos esquinas en coordenadas "
            "del dibujo (ZoomWindow COM nativo, sin SendCommand). NO PROBADA aun."
        ),
    )
    async def zoom_ventana(x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.Application.ZoomWindow(_punto(x1, y1), _punto(x2, y2))
                return {"success": True, "esquina1": [x1, y1], "esquina2": [x2, y2]}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_centro",
        description=(
            "Centra la vista en un punto con una altura de vista dada en unidades de "
            "dibujo (ZoomCenter COM nativo, sin SendCommand). alto_vista pequeno = mas "
            "zoom. NO PROBADA aun."
        ),
    )
    async def zoom_centro(x: float, y: float, alto_vista: float) -> dict[str, Any]:
        try:
            def _run():
                client.active_doc.Application.ZoomCenter(_punto(x, y), alto_vista)
                return {"success": True, "centro": [x, y], "alto_vista": alto_vista}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="zoom_objeto",
        description=(
            "Encuadra la vista sobre un objeto concreto identificado por su handle: "
            "bounding box real del objeto + margen porcentual + ZoomWindow (todo COM "
            "nativo, sin SendCommand). LECCION: en bloques rotados el bounding box "
            "sobre-estima el area (limitacion heredada de GetBoundingBox). NO PROBADA aun."
        ),
    )
    async def zoom_objeto(handle: str, margen: float = 0.15) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                obj = doc.HandleToObject(handle)
                min_pt, max_pt = obj.GetBoundingBox()
                dx = (max_pt[0] - min_pt[0]) * margen
                dy = (max_pt[1] - min_pt[1]) * margen
                # margen minimo absoluto por si el objeto es puntual/degenerado
                dx = max(dx, 0.5)
                dy = max(dy, 0.5)
                doc.Application.ZoomWindow(
                    _punto(min_pt[0] - dx, min_pt[1] - dy),
                    _punto(max_pt[0] + dx, max_pt[1] + dy),
                )
                return {
                    "success": True,
                    "handle": handle,
                    "bbox_min": [min_pt[0], min_pt[1]],
                    "bbox_max": [max_pt[0], max_pt[1]],
                    "margen": margen,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="vista_planta",
        description=(
            "Activa la vista en planta (vista superior, SCP mundo). COM nativo "
            "(ActiveViewport.Direction = (0,0,1) + reasignacion del viewport "
            "activo, obligatoria para que el cambio surta efecto), sin SendCommand."
        ),
    )
    async def vista_planta() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                viewport = doc.ActiveViewport
                viewport.Direction = _punto(0, 0, 1)
                doc.ActiveViewport = viewport
                return {"success": True, "mensaje": "Vista planta activada"}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="vista_isometrica_sw",
        description=(
            "Activa la vista isometrica SW (suroeste). Util para ver superficies "
            "3D. COM nativo (ActiveViewport.Direction = (-1,-1,1) + reasignacion "
            "del viewport activo, obligatoria para que el cambio surta efecto), "
            "sin SendCommand."
        ),
    )
    async def vista_isometrica_sw() -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                viewport = doc.ActiveViewport
                viewport.Direction = _punto(-1, -1, 1)
                doc.ActiveViewport = viewport
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
