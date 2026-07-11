"""
tools_mesh.py  -  Crear mallas 3D (3DFace) desde polilineas en Civil 3D
Dos estrategias:
  1) crear_malla_desde_triangulacion: detecta triangulos por adyacencia de aristas
     (para capas con lineas sueltas formando una triangulacion explicita)
  2) crear_malla_desde_polilineas: cada polilinea (cerrada o abierta) se convierte
     directamente en una o varias 3DFace, sin necesidad de triangulacion explicita.
     Usa fan triangulation para contornos de mas de 4 vertices.
"""
from __future__ import annotations
import logging
import time
from collections import defaultdict
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.mesh")


def _punto_clave(pt, tol=3):
    return (round(float(pt[0]), tol), round(float(pt[1]), tol), round(float(pt[2]), tol))


# ─── Estrategia 1: triangulacion por adyacencia de aristas ───────────────────

def _extraer_segmentos(model, capa_origen: str):
    segmentos = []
    for i in range(model.Count):
        try:
            obj = model.Item(i)
            if obj.Layer.lower() != capa_origen.lower():
                continue
            nombre = obj.ObjectName
            if nombre == "AcDbLine":
                p1 = tuple(obj.StartPoint)
                p2 = tuple(obj.EndPoint)
                segmentos.append((p1, p2))
            elif nombre in ("AcDb3dPolyline", "AcDb2dPolyline",
                            "AcDbPolyline", "AcDbLwPolyline"):
                raw = list(obj.Coordinates)
                if nombre == "AcDbLwPolyline":
                    pts = [(raw[j], raw[j+1], 0.0) for j in range(0, len(raw), 2)]
                else:
                    pts = [(raw[j], raw[j+1], raw[j+2]) for j in range(0, len(raw), 3)]
                for k in range(len(pts) - 1):
                    segmentos.append((pts[k], pts[k+1]))
                try:
                    if obj.Closed and len(pts) > 1:
                        segmentos.append((pts[-1], pts[0]))
                except Exception:
                    pass
        except Exception:
            continue
    return segmentos


def _detectar_triangulos(segmentos):
    vertices = []
    vertice_idx = {}

    def idx(pt):
        k = _punto_clave(pt)
        if k not in vertice_idx:
            vertice_idx[k] = len(vertices)
            vertices.append(k)
        return vertice_idx[k]

    aristas = set()
    for p1, p2 in segmentos:
        i1, i2 = idx(p1), idx(p2)
        if i1 != i2:
            aristas.add((min(i1, i2), max(i1, i2)))

    adj = defaultdict(set)
    for i1, i2 in aristas:
        adj[i1].add(i2)
        adj[i2].add(i1)

    triangulos = set()
    for v0 in range(len(vertices)):
        vecinos = sorted(adj[v0])
        for a in range(len(vecinos)):
            for b in range(a + 1, len(vecinos)):
                va, vb = vecinos[a], vecinos[b]
                if vb in adj[va]:
                    triangulos.add(tuple(sorted([v0, va, vb])))

    return vertices, list(triangulos)


# ─── Estrategia 2: cada polilinea -> cara(s) directamente ────────────────────

def _extraer_polilineas(model, capa_origen: str):
    """Devuelve lista de listas de vertices (uno por polilinea), sin tocar lineas sueltas."""
    polilineas = []
    for i in range(model.Count):
        try:
            obj = model.Item(i)
            if obj.Layer.lower() != capa_origen.lower():
                continue
            nombre = obj.ObjectName
            if nombre not in ("AcDb3dPolyline", "AcDb2dPolyline",
                              "AcDbPolyline", "AcDbLwPolyline"):
                continue
            raw = list(obj.Coordinates)
            if nombre == "AcDbLwPolyline":
                pts = [(raw[j], raw[j+1], 0.0) for j in range(0, len(raw), 2)]
            else:
                pts = [(raw[j], raw[j+1], raw[j+2]) for j in range(0, len(raw), 3)]
            polilineas.append(pts)
        except Exception:
            continue
    return polilineas


def _limpiar_vertices(pts):
    """Elimina vertices duplicados consecutivos y cierre repetido (primero == ultimo)."""
    limpio = []
    for p in pts:
        if not limpio or _punto_clave(limpio[-1]) != _punto_clave(p):
            limpio.append(p)
    if len(limpio) > 1 and _punto_clave(limpio[0]) == _punto_clave(limpio[-1]):
        limpio.pop()
    return limpio


def _generar_caras(pts):
    """
    A partir de un contorno (cerrado o no), genera caras de hasta 4 vertices.
    N=2 -> ninguna cara (un segmento no forma superficie)
    N=3 -> un triangulo
    N=4 -> un cuadrilatero (3DFACE soporta 4 puntos nativamente)
    N>4 -> fan triangulation desde el primer vertice
    """
    n = len(pts)
    if n < 3:
        return []
    if n in (3, 4):
        return [pts]
    caras = []
    v0 = pts[0]
    for i in range(1, n - 1):
        caras.append([v0, pts[i], pts[i + 1]])
    return caras


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="crear_malla_desde_triangulacion",
        description=(
            "Convierte la triangulacion 3D de una capa en caras 3D (3DFace) via COM puro. "
            "Lee lineas y polilineas 3D de capa_origen, detecta triangulos por adyacencia "
            "de aristas (asume malla triangulada explicita) y crea una 3DFace por triangulo "
            "en capa_destino. Usar cuando la geometria origen es una triangulacion clasica "
            "(un contorno + diagonales internas)."
        ),
    )
    async def crear_malla_desde_triangulacion(
        capa_origen: str,
        capa_destino: str,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                ms = doc.ModelSpace

                nombres_capas = [doc.Layers.Item(i).Name.lower()
                                 for i in range(doc.Layers.Count)]
                if capa_destino.lower() not in nombres_capas:
                    nueva = doc.Layers.Add(capa_destino)
                    nueva.color = 3

                segmentos = _extraer_segmentos(ms, capa_origen)
                if not segmentos:
                    return {"error": f"No se encontraron objetos en la capa '{capa_origen}'"}

                vertices, triangulos = _detectar_triangulos(segmentos)
                if not triangulos:
                    return {
                        "error": "No se detectaron triangulos.",
                        "vertices": len(vertices),
                        "segmentos": len(segmentos),
                    }

                cmd = f"_UCS\n_W\n_CLAYER\n{capa_destino}\n"
                for tri in triangulos:
                    a = vertices[tri[0]]
                    b = vertices[tri[1]]
                    c = vertices[tri[2]]
                    cmd += (
                        f"_3DFACE\n"
                        f"{a[0]},{a[1]},{a[2]}\n"
                        f"{b[0]},{b[1]},{b[2]}\n"
                        f"{c[0]},{c[1]},{c[2]}\n"
                        f"{c[0]},{c[1]},{c[2]}\n"
                        f"\n"
                    )

                doc.SendCommand(cmd)
                time.sleep(1.0 + len(triangulos) * 0.1)

                return {
                    "success": True,
                    "capa_destino": capa_destino,
                    "vertices": len(vertices),
                    "caras_enviadas": len(triangulos),
                }

            return await run_com(_run)
        except Exception as exc:
            log.exception("crear_malla_desde_triangulacion")
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_malla_desde_polilineas",
        description=(
            "Convierte cada polilinea de una capa directamente en una o varias 3DFace, "
            "sin necesidad de triangulacion explicita por adyacencia. Cada polilinea "
            "(cerrada o abierta) se trata como un contorno independiente: 3 vertices -> "
            "triangulo, 4 vertices -> cuadrilatero, mas de 4 -> fan triangulation desde "
            "el primer vertice. Segmentos sueltos de 2 vertices se ignoran (no forman cara). "
            "Usar cuando la geometria origen son varios contornos/caras ya definidos "
            "(p.ej. peldanos de una escalera) en lugar de una triangulacion clasica."
        ),
    )
    async def crear_malla_desde_polilineas(
        capa_origen: str,
        capa_destino: str,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                ms = doc.ModelSpace

                nombres_capas = [doc.Layers.Item(i).Name.lower()
                                 for i in range(doc.Layers.Count)]
                if capa_destino.lower() not in nombres_capas:
                    nueva = doc.Layers.Add(capa_destino)
                    nueva.color = 3

                polilineas = _extraer_polilineas(ms, capa_origen)
                if not polilineas:
                    return {"error": f"No se encontraron polilineas en la capa '{capa_origen}'"}

                todas_caras = []
                ignoradas = 0
                for pts in polilineas:
                    limpio = _limpiar_vertices(pts)
                    caras = _generar_caras(limpio)
                    if not caras:
                        ignoradas += 1
                    todas_caras.extend(caras)

                if not todas_caras:
                    return {
                        "error": "Ninguna polilinea genero caras validas (todas tienen <3 vertices unicos).",
                        "polilineas_leidas": len(polilineas),
                    }

                cmd = f"_UCS\n_W\n_CLAYER\n{capa_destino}\n"
                for cara in todas_caras:
                    pts4 = cara if len(cara) == 4 else cara + [cara[-1]]
                    coords = "\n".join(f"{p[0]},{p[1]},{p[2]}" for p in pts4)
                    cmd += f"_3DFACE\n{coords}\n\n"

                doc.SendCommand(cmd)
                time.sleep(1.0 + len(todas_caras) * 0.1)

                return {
                    "success": True,
                    "capa_destino": capa_destino,
                    "polilineas_leidas": len(polilineas),
                    "polilineas_ignoradas": ignoradas,
                    "caras_enviadas": len(todas_caras),
                }

            return await run_com(_run)
        except Exception as exc:
            log.exception("crear_malla_desde_polilineas")
            return {"error": str(exc)}
