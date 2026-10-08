"""
tools_historial.py  -  Lectura del historial de comandos via archivo de registro
Usa las variables de sistema LOGFILEMODE / LOGFILENAME: sin rutas hardcodeadas,
la ruta del log sale siempre de GetVariable (portable entre usuarios y maquinas).
Validado en POC 2026-07-17: latencia cero (AutoCAD vuelca al log comando a comando)
y el ciclo off/on de LOGFILEMODE reutiliza el mismo archivo dentro de la sesion.
"""
from __future__ import annotations
import os
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

MAX_LINEAS = 500


def _tail(path: str, n: int) -> tuple[list[str], int]:
    """Devuelve (ultimas n lineas, total de lineas). Log en ANSI (cp1252)."""
    with open(path, "r", encoding="cp1252", errors="replace") as f:
        lineas = f.readlines()
    return [ln.rstrip("\n") for ln in lineas[-n:]], len(lineas)


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="leer_historial_comandos",
        description=(
            "Lee las ultimas n lineas del historial de la consola de comandos de Civil 3D "
            "(archivo .log controlado por LOGFILEMODE). Si el registro esta desactivado, NO lo "
            "activa: devuelve error avisando de que hay que activarlo primero con "
            "activar_historial_comandos. Util para verificar el resultado real de SendCommand / "
            "ejecutar_lisp: el log captura tanto el comando como su salida, incluidos mensajes de error. "
            "Por defecto (marcar_tras_leer=True), tras leer hace un ciclo LOGFILEMODE off/on que "
            "inserta una marca de timestamp de AutoCAD ('[ AutoCAD - <fecha/hora> ]') en el log; "
            "sirve de marcador periodico para que la siguiente lectura pueda identificar que es "
            "nuevo desde la anterior. Pasar marcar_tras_leer=False para una lectura sin efecto lateral. "
            "LECCION: la ruta del log se obtiene siempre de LOGFILENAME (solo lectura, incluye "
            "sufijo aleatorio por sesion, p.ej. Dibujo1_184356c5c.log); nunca construirla a mano. "
            "El volcado a disco es inmediato tras cada comando (latencia cero, validado en 2021)."
        ),
    )
    async def leer_historial_comandos(n_lineas: int = 20, marcar_tras_leer: bool = True) -> dict[str, Any]:
        try:
            def _run():
                n = max(1, min(int(n_lineas), MAX_LINEAS))
                doc = client.active_doc
                if int(doc.GetVariable("LOGFILEMODE")) != 1:
                    return {
                        "error": "El registro de la consola esta desactivado (LOGFILEMODE=0). "
                                 "Activalo con la herramienta activar_historial_comandos antes de "
                                 "poder leer el historial.",
                    }
                archivo = doc.GetVariable("LOGFILENAME")
                if not archivo or not os.path.isfile(archivo):
                    return {
                        "error": "El archivo de registro aun no existe. "
                                 "Se creara con el proximo comando ejecutado en la consola.",
                        "archivo": archivo or None,
                    }
                lineas, total = _tail(archivo, n)
                res = {
                    "archivo": archivo,
                    "total_lineas": total,
                    "devueltas": len(lineas),
                    "lineas": lineas,
                }
                if marcar_tras_leer:
                    doc.SetVariable("LOGFILEMODE", 0)
                    doc.SetVariable("LOGFILEMODE", 1)
                    res["marcador_insertado"] = True
                return res
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="activar_historial_comandos",
        description=(
            "Activa o desactiva el registro en archivo del historial de la consola de comandos "
            "(variable de sistema LOGFILEMODE, 0/1). activar=True lo enciende; activar=False lo "
            "apaga. Devuelve el estado resultante y, si esta activo, la ruta del archivo .log "
            "(LOGFILENAME). El registro solo contiene lo ocurrido desde el momento de activacion "
            "en adelante. Necesario ejecutar antes de leer_historial_comandos si esta desactivado."
        ),
    )
    async def activar_historial_comandos(activar: bool = True) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                estado_previo = int(doc.GetVariable("LOGFILEMODE"))
                doc.SetVariable("LOGFILEMODE", 1 if activar else 0)
                estado_actual = int(doc.GetVariable("LOGFILEMODE"))
                res = {
                    "logfilemode_previo": estado_previo,
                    "logfilemode_actual": estado_actual,
                    "activado": bool(estado_actual),
                }
                if estado_actual:
                    res["archivo"] = doc.GetVariable("LOGFILENAME")
                return res
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
