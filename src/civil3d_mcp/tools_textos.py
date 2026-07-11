"""
tools_textos.py  -  Busqueda de textos y resaltado temporal de objetos
- buscar_textos: localiza entidades con TextString (Text, MText, Attribute, MLeader...)
  que coincidan con un patron. Usa la cache SQLite si la capa esta escaneada; si no, COM directo.
- resaltar_objetos: Highlight temporal por handles (se pierde al regenerar/seleccionar).
  No toca capas ni colores reales.
"""
from __future__ import annotations
import json
import logging
import os
import re
import sqlite3
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError
from .tools_cache import _db_path_for

log = logging.getLogger("civil3d_mcp.tools.textos")

MAX_RESULTADOS = 200


def _coincide(texto: str, patron: str, es_regex: bool) -> bool:
    if es_regex:
        return re.search(patron, texto, re.IGNORECASE) is not None
    return patron.lower() in texto.lower()


def _buscar_en_cache(db_path: str, capa: str, patron: str, es_regex: bool):
    """Devuelve (resultados, timestamp_escaneo) o None si la capa no esta escaneada."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT timestamp FROM escaneos WHERE lower(capa) = lower(?)", (capa,)
        )
        fila = cur.fetchone()
        if not fila:
            return None
        timestamp = fila[0]
        cur = conn.execute(
            "SELECT handle, tipo, capa, texto, punto_insercion FROM entidades "
            "WHERE lower(capa) = lower(?) AND texto IS NOT NULL",
            (capa,),
        )
        resultados = []
        for handle, tipo, capa_obj, texto, pin in cur:
            if not _coincide(texto, patron, es_regex):
                continue
            resultados.append({
                "handle": handle,
                "tipo": tipo,
                "capa": capa_obj,
                "texto": texto,
                "punto_insercion": json.loads(pin) if pin else None,
            })
            if len(resultados) >= MAX_RESULTADOS:
                break
        return resultados, timestamp
    finally:
        conn.close()


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="buscar_textos",
        description=(
            "Busca entidades con texto (Text, MText, Attribute, MLeader...) cuyo TextString coincida "
            "con un patron (subcadena sin distinguir mayusculas, o regex si regex=True). Si se indica "
            "capa y esta escaneada en la BD (escanear_capa_a_db), lee de la cache (rapido, incluye "
            "timestamp del escaneo); si no, escanea ModelSpace via COM. Devuelve handle, tipo, capa, "
            "texto y punto de insercion (maximo 200). Util para erratas de guitarra, codigos duplicados, etc."
        ),
    )
    async def buscar_textos(patron: str, capa: str = "", regex: bool = False) -> dict[str, Any]:
        try:
            def _run():
                if regex:
                    try:
                        re.compile(patron)
                    except re.error as e:
                        return {"error": f"Regex invalida: {e}"}
                doc = client.active_doc
                # 1) Intento por cache si hay capa y BD
                if capa:
                    db_path = _db_path_for(doc)
                    if os.path.isfile(db_path):
                        try:
                            hit = _buscar_en_cache(db_path, capa, patron, regex)
                        except Exception as e:
                            log.warning(f"Cache fallo ({e}), usando COM directo")
                            hit = None
                        if hit is not None:
                            resultados, timestamp = hit
                            return {
                                "fuente": "cache",
                                "escaneado_en": timestamp,
                                "total": len(resultados),
                                "resultados": resultados,
                            }
                # 2) COM directo
                ms = doc.ModelSpace
                resultados = []
                for obj in ms:
                    try:
                        if capa and obj.Layer.lower() != capa.lower():
                            continue
                        texto = obj.TextString
                        if not texto or not _coincide(texto, patron, regex):
                            continue
                        info = {
                            "handle": obj.Handle,
                            "tipo": obj.ObjectName,
                            "capa": obj.Layer,
                            "texto": texto,
                        }
                        try:
                            info["punto_insercion"] = list(obj.InsertionPoint)
                        except Exception:
                            info["punto_insercion"] = None
                        resultados.append(info)
                        if len(resultados) >= MAX_RESULTADOS:
                            break
                    except Exception:
                        pass
                return {"fuente": "com", "total": len(resultados), "resultados": resultados}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="seleccionar_objetos",
        description=(
            "Selecciona visualmente (grips azules) una lista de objetos por handle, via sssetfirst LISP. "
            "activar=True establece la seleccion activa; activar=False la limpia (sssetfirst nil nil). "
            "La seleccion se pierde si el usuario hace clic en el dibujo. No modifica capas ni colores."
        ),
    )
    async def seleccionar_objetos(handles: list[str], activar: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                if not activar:
                    doc.SendCommand("(sssetfirst nil nil) ")
                    return {"accion": "quitar_resalte", "total_ok": 0, "ok": [], "fallos": []}
                ok = []
                fallos = []
                for h in handles:
                    try:
                        doc.HandleToObject(h)
                        ok.append(h)
                    except Exception as exc:
                        fallos.append({"handle": h, "error": str(exc)})
                if not ok:
                    return {"accion": "resaltar", "total_ok": 0, "ok": [], "fallos": fallos}
                # Construir ssadd anidado de dentro hacia fuera
                lisp = "(ssadd)"
                for h in reversed(ok):
                    lisp = f'(ssadd (handent "{h}") {lisp})'
                doc.SendCommand(f"(sssetfirst nil {lisp}) ")
                return {
                    "accion": "resaltar",
                    "total_ok": len(ok),
                    "ok": ok,
                    "fallos": fallos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="seleccionar_por_filtro",
        description=(
            "Selecciona visualmente (grips azules) todos los objetos de ModelSpace que cumplan los "
            "filtros indicados: capa (exacto, case-insensitive), tipo (ObjectName, p.ej. 'AcDbLine', "
            "'AcDb3dPolyline', 'AcDbText'; case-insensitive), color ACI (entero 1-255). Filtros "
            "acumulativos (AND). Al menos uno debe especificarse. Sin necesidad de escanear antes. "
            "Devuelve los handles seleccionados y el total."
        ),
    )
    async def seleccionar_por_filtro(
        capa: str = "",
        tipo: str = "",
        color: int = 0,
    ) -> dict[str, Any]:
        try:
            def _run():
                if not capa and not tipo and not color:
                    return {"error": "Especifica al menos un filtro: capa, tipo o color."}
                ms = client.model_space
                ok = []
                for obj in ms:
                    try:
                        if capa and obj.Layer.lower() != capa.lower():
                            continue
                        if tipo and obj.ObjectName.lower() != tipo.lower():
                            continue
                        if color:
                            try:
                                obj_color = int(obj.color)
                            except Exception:
                                continue
                            if obj_color != color:
                                continue
                        ok.append(obj.Handle)
                    except Exception:
                        pass
                if not ok:
                    return {"total": 0, "handles": [], "mensaje": "Ningun objeto coincide con los filtros."}
                lisp = "(ssadd)"
                for h in reversed(ok):
                    lisp = f'(ssadd (handent "{h}") {lisp})'
                client.active_doc.SendCommand(f"(sssetfirst nil {lisp}) ")
                return {
                    "total": len(ok),
                    "handles": ok,
                    "filtros": {
                        "capa": capa or None,
                        "tipo": tipo or None,
                        "color": color or None,
                    },
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="ejecutar_lisp",
        description=(
            "Ejecuta codigo AutoLISP arbitrario en Civil 3D via SendCommand. Util para operaciones "
            "puntuales que no tienen herramienta dedicada: leer variables de sistema, consultar Xdata, "
            "probar LISP experimental, etc. El codigo se envia tal cual — usar con cuidado. "
            "Inspirado en execute_lisp de puran-water/autocad-mcp, reimplementado via SendCommand "
            "en lugar de File IPC. No captura el valor de retorno del LISP (limitacion de SendCommand)."
        ),
    )
    async def ejecutar_lisp(codigo: str) -> dict[str, Any]:
        try:
            def _run():
                if not codigo or not codigo.strip():
                    return {"error": "El parametro codigo no puede estar vacio."}
                doc = client.active_doc
                # Asegurar que el codigo termina en espacio (patron SendCommand)
                cmd = codigo.strip()
                if not cmd.endswith(" "):
                    cmd += " "
                doc.SendCommand(cmd)
                return {
                    "enviado": codigo.strip(),
                    "nota": "SendCommand no devuelve el valor de retorno LISP. "
                            "Para capturar resultados usa escritura a fichero desde el propio LISP.",
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
