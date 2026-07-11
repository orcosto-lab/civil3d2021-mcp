"""
tools_cache.py  -  Cache SQLite de entidades del dibujo
Escanea capas completas de ModelSpace a una BD SQLite local (fuera de Google Drive)
para consultas sin el limite de 100 de listar_objetos y sin releer COM.
BD: una por dibujo, en D:\\ZZZ Topografia\\Temp Civil IA\\<nombre_dwg>.sqlite
Cada escaneo de capa REEMPLAZA las filas previas de esa capa (datos con timestamp:
recordar que Pedro edita el dibujo en paralelo y la cache caduca rapido).
"""
from __future__ import annotations
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.cache")

DB_DIR = r"D:\ZZZ Topografia\Temp Civil IA"
MAX_FILAS_CONSULTA = 500


def _db_path_for(doc) -> str:
    """Ruta de la BD SQLite asociada al dibujo activo (una BD por dibujo)."""
    nombre = "sin_nombre"
    try:
        nombre = doc.Name or "sin_nombre"
    except Exception:
        pass
    base = re.sub(r"\.dwg$", "", nombre, flags=re.IGNORECASE)
    base = re.sub(r'[<>:"/\\|?*]', "_", base).strip() or "sin_nombre"
    return os.path.join(DB_DIR, base + ".sqlite")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS entidades (
            handle TEXT PRIMARY KEY,
            tipo TEXT,
            capa TEXT,
            color INTEGER,
            texto TEXT,
            punto_insercion TEXT,
            vertices TEXT,
            num_vertices INTEGER,
            escaneado_en TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS escaneos (
            capa TEXT PRIMARY KEY,
            timestamp TEXT,
            total INTEGER
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entidades_capa ON entidades(capa)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entidades_tipo ON entidades(tipo)")


def _extraer_vertices(obj, tipo: str):
    """Vertices como lista de [x,y] o [x,y,z] segun el tipo de entidad."""
    try:
        if tipo == "AcDbLine":
            return [list(obj.StartPoint), list(obj.EndPoint)]
        coords = list(obj.Coordinates)
        # AcDbPolyline (LWPolyline) usa pares 2D; 2d/3dPolyline usan tripletas
        paso = 2 if tipo == "AcDbPolyline" else 3
        return [list(coords[i:i + paso]) for i in range(0, len(coords), paso)]
    except Exception:
        return None


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="escanear_capa_a_db",
        description=(
            "Escanea TODOS los objetos de una capa de ModelSpace (sin limite de 100) y los vuelca "
            "a una BD SQLite local (una por dibujo, en D:\\ZZZ Topografia\\Temp Civil IA). Guarda handle, "
            "tipo, capa, color, TextString, punto de insercion y vertices (JSON). Reemplaza los datos "
            "previos de esa capa. Consultar despues con consultar_db. Para vistazos rapidos de <100 "
            "objetos usar listar_objetos (mas ligero)."
        ),
    )
    async def escanear_capa_a_db(capa: str, incluir_vertices: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                ms = doc.ModelSpace
                db_path = _db_path_for(doc)
                os.makedirs(DB_DIR, exist_ok=True)
                ahora = datetime.now().isoformat(timespec="seconds")
                filas = []
                por_tipo: dict[str, int] = {}
                con_texto = 0
                for obj in ms:
                    try:
                        capa_obj = obj.Layer
                        if capa_obj.lower() != capa.lower():
                            continue
                        tipo = obj.ObjectName
                        handle = obj.Handle
                        color = None
                        try:
                            color = int(obj.color)
                        except Exception:
                            pass
                        texto = None
                        try:
                            texto = obj.TextString
                            con_texto += 1
                        except Exception:
                            pass
                        pin = None
                        try:
                            pin = json.dumps(list(obj.InsertionPoint))
                        except Exception:
                            pass
                        verts = _extraer_vertices(obj, tipo) if incluir_vertices else None
                        filas.append((
                            handle, tipo, capa_obj, color, texto, pin,
                            json.dumps(verts) if verts else None,
                            len(verts) if verts else None,
                            ahora,
                        ))
                        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
                    except Exception:
                        pass
                conn = sqlite3.connect(db_path)
                try:
                    _ensure_schema(conn)
                    conn.execute("DELETE FROM entidades WHERE lower(capa) = lower(?)", (capa,))
                    conn.executemany(
                        "INSERT OR REPLACE INTO entidades VALUES (?,?,?,?,?,?,?,?,?)", filas
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO escaneos VALUES (?,?,?)",
                        (capa, ahora, len(filas)),
                    )
                    conn.commit()
                finally:
                    conn.close()
                return {
                    "db": db_path,
                    "capa": capa,
                    "total": len(filas),
                    "por_tipo": por_tipo,
                    "con_texto": con_texto,
                    "timestamp": ahora,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="consultar_db",
        description=(
            "Ejecuta una consulta SQL de SOLO LECTURA (SELECT) sobre la BD SQLite del dibujo activo "
            "(creada con escanear_capa_a_db). Tablas: entidades(handle, tipo, capa, color, texto, "
            "punto_insercion, vertices, num_vertices, escaneado_en) y escaneos(capa, timestamp, total). "
            "punto_insercion y vertices son JSON. Devuelve maximo 500 filas. Los datos son una foto del "
            "momento del escaneo: si el dibujo ha cambiado, re-escanear antes."
        ),
    )
    async def consultar_db(sql: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                db_path = _db_path_for(doc)
                if not os.path.isfile(db_path):
                    return {"error": f"No existe BD para este dibujo ({db_path}). Usar escanear_capa_a_db primero."}
                sql_limpio = sql.strip().rstrip(";").strip()
                if ";" in sql_limpio:
                    return {"error": "Solo se permite una unica sentencia SQL."}
                if not re.match(r"^(select|with)\b", sql_limpio, re.IGNORECASE):
                    return {"error": "Solo se permiten consultas SELECT (o WITH ... SELECT)."}
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                try:
                    cur = conn.execute(sql_limpio)
                    columnas = [d[0] for d in cur.description] if cur.description else []
                    filas = cur.fetchmany(MAX_FILAS_CONSULTA + 1)
                finally:
                    conn.close()
                truncado = len(filas) > MAX_FILAS_CONSULTA
                filas = filas[:MAX_FILAS_CONSULTA]
                return {
                    "db": db_path,
                    "columnas": columnas,
                    "total_devuelto": len(filas),
                    "truncado_a_500": truncado,
                    "filas": [list(f) for f in filas],
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
