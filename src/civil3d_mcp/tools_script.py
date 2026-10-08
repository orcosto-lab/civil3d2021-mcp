"""
tools_script.py  -  Ejecucion de scripts .scr y carga de plugins .NET en Civil 3D
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import logging
import os
import time
import pythoncom
import win32com.client
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.script")

_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
)


def _ensure_scripts_dir() -> str:
    os.makedirs(_SCRIPTS_DIR, exist_ok=True)
    return _SCRIPTS_DIR


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="listar_scripts",
        description="Lista todos los scripts .scr disponibles en la carpeta scripts/ del servidor MCP.",
    )
    async def listar_scripts() -> dict[str, Any]:
        try:
            def _run():
                scripts_dir = _ensure_scripts_dir()
                archivos = [f for f in os.listdir(scripts_dir) if f.endswith(".scr")]
                return {"total": len(archivos), "scripts": archivos, "carpeta": scripts_dir}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="ejecutar_script",
        description=(
            "Ejecuta un script .scr de la carpeta scripts/ del MCP en Civil 3D. "
            "Usa FILEDIA=0 para evitar dialogos. Ejemplo: nombre_script='crear_malla.scr' "
            "LECCION: los cambios de capa DENTRO del .scr no son fiables - los objetos suelen "
            "caer en capa 0. Crear primero y reasignar despues con cambiar_capa_objetos. "
            "Para polilineas 3D con cota real usar el comando _3DPOLY dentro del script (NO 3DPOL, "
            "ese comando no existe en Civil 3D 2021 espanol - verificado en vivo 03/08/2026). "
            "LECCION: esta tool va por SendCommand y puede fallar sin devolver error - tras "
            "ejecutarla, verificar el resultado real con leer_historial_comandos; si el registro "
            "esta desactivado, pedir autorizacion para activar_historial_comandos (nunca activarlo sin avisar)."
        ),
    )
    async def ejecutar_script(nombre_script: str) -> dict[str, Any]:
        scripts_dir = _ensure_scripts_dir()
        ruta = os.path.join(scripts_dir, nombre_script).replace("\\", "/")
        if not os.path.exists(os.path.join(scripts_dir, nombre_script)):
            return {"error": f"Script no encontrado: {ruta}"}
        loop = asyncio.get_event_loop()

        def _send():
            try:
                pythoncom.CoInitialize()
                acad = win32com.client.Dispatch("AutoCAD.Application")
                doc = acad.ActiveDocument
                doc.SendCommand(f"FILEDIA\n0\nSCRIPT\n{ruta}\nFILEDIA\n1\n")
                time.sleep(3)
                return {"success": True, "script": ruta}
            except Exception as e:
                return {"error": str(e)}
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        dedicated = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(dedicated, _send),
                timeout=30.0,
            )
            return result
        except asyncio.TimeoutError:
            return {"warning": "Script tardo >30s. Comprueba Civil 3D."}
        finally:
            dedicated.shutdown(wait=False)

    @mcp.tool(
        name="cargar_plugin_dll",
        description=(
            "Carga un plugin .NET (.dll) en Civil 3D via NETLOAD (FILEDIA=0). "
            "Usa executor dedicado — no bloquea el hilo COM principal aunque NETLOAD tarde. "
            "Timeout: 20 s. Si hay dialogo abierto, devuelve aviso sin colgar el servidor. "
            "LECCION: OBLIGATORIO ejecutar esta tool tras cada reinicio de Claude Desktop "
            "antes de usar cualquier tool de civil3d-sacred (el plugin no persiste). "
            "Solo funciona con Civil 3D 2023+ (NO en P101, que tiene 2021). "
            "LECCION: esta tool va por SendCommand y puede fallar sin devolver error - tras "
            "ejecutarla, verificar el resultado real con leer_historial_comandos; si el registro "
            "esta desactivado, pedir autorizacion para activar_historial_comandos (nunca activarlo sin avisar)."
        ),
    )
    async def cargar_plugin_dll(ruta_dll: str) -> dict[str, Any]:
        ruta = ruta_dll.replace("\\", "/")
        loop = asyncio.get_running_loop()

        def _send() -> dict[str, Any]:
            try:
                pythoncom.CoInitialize()
                acad = win32com.client.Dispatch("AutoCAD.Application")
                doc = acad.ActiveDocument
                doc.SendCommand(f"FILEDIA\n0\nNETLOAD\n{ruta}\nFILEDIA\n1\n")
                time.sleep(0.5)
                return {"success": True, "plugin_cargado": ruta_dll}
            except Exception as e:
                return {"error": str(e)}
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        dedicated = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(dedicated, _send),
                timeout=20.0,
            )
            return result
        except asyncio.TimeoutError:
            return {
                "warning": (
                    "NETLOAD tardo >20 s. Posible dialogo abierto en Civil 3D — pulsa Escape."
                ),
                "ruta": ruta_dll,
            }
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            dedicated.shutdown(wait=False)
