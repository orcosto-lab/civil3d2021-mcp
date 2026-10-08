"""
tools_hidrologia_superficie.py  -  Analisis hidrologico basado en muestreo de una
TIN Surface via COM (FindElevationAtXY).

LECCION GENERAL DE ARQUITECTURA: en sacred (plugin .NET in-process) estas
operaciones recorren la superficie en memoria sin coste de IPC. Aqui cada
elevacion cuesta una llamada COM real (marshalling incluido). Un trazado de
flujo o una delineacion de cuenca "ingenuos" (una llamada por celda de una
malla fina) pueden disparar miles de llamadas COM y tardar minutos o colgar
la sesion. Todas las tools de este modulo imponen topes duros de numero de
muestras y fuerzan al llamante a elegir una resolucion de malla acorde al
area de interes real (no al area total del proyecto). Esto es una limitacion
de arquitectura real, no un descuido: si se necesita analisis de cuencas a
resolucion fina sobre areas grandes, hace falta la via pythonnet/.NET.
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.hidrologia_superficie")

_DIRECCIONES_D8 = []
for _dx, _dy in ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)):
    _norma = math.hypot(_dx, _dy)
    _DIRECCIONES_D8.append((_dx / _norma, _dy / _norma))


def _buscar_superficie(client: Civil3DClient, nombre: str):
    for surf in client._doc.Surfaces:
        if surf.Name == nombre:
            return surf
    return None


def _elevacion_segura(surf, x: float, y: float) -> float | None:
    """FindElevationAtXY, devolviendo None (en vez de lanzar) si el punto
    cae fuera del limite de la superficie (PointNotOnEntityException COM)."""
    try:
        return surf.FindElevationAtXY(x, y)
    except Exception:
        return None


def _trazar_descenso(surf, x: float, y: float, paso_m: float, max_pasos: int):
    """Traza D8 de descenso mas pronunciado desde (x,y). Devuelve la lista de
    puntos {x,y,z} recorridos (incluye el punto inicial), o None si el punto
    inicial ya esta fuera de la superficie. Se detiene al llegar a un
    sumidero local (ningun vecino mas bajo) o al agotar max_pasos."""
    z = _elevacion_segura(surf, x, y)
    if z is None:
        return None
    ruta = [{"x": x, "y": y, "z": z}]
    for _ in range(max_pasos):
        mejor = None
        mejor_z = z
        for ux, uy in _DIRECCIONES_D8:
            nx, ny = x + ux * paso_m, y + uy * paso_m
            nz = _elevacion_segura(surf, nx, ny)
            if nz is not None and nz < mejor_z:
                mejor_z = nz
                mejor = (nx, ny, nz)
        if mejor is None:
            break
        x, y, z = mejor
        ruta.append({"x": x, "y": y, "z": z})
    return ruta


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="trazar_flujo",
        description=(
            "Traza la linea de flujo de escorrentia superficial desde un punto, siguiendo "
            "en cada paso la direccion de maxima pendiente descendente entre 8 vecinos "
            "(algoritmo D8, estandar en analisis hidrologico GIS) hasta encontrar un "
            "sumidero local o agotar max_pasos. "
            "LECCION: cada paso cuesta hasta 8 llamadas COM a Surface.FindElevationAtXY "
            "(una por vecino); max_pasos esta topado a 500 para evitar tiempos de espera "
            "excesivos (500 pasos = hasta 4000 llamadas COM). Para trazados largos, sube "
            "paso_m en vez de max_pasos."
        ),
    )
    async def trazar_flujo(
        nombre_superficie: str,
        x_inicio: float,
        y_inicio: float,
        paso_m: float = 5.0,
        max_pasos: int = 200,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                tope = min(max(1, max_pasos), 500)
                ruta = _trazar_descenso(surf, x_inicio, y_inicio, paso_m, tope)
                if ruta is None:
                    return {"error": "El punto de inicio esta fuera de la superficie."}
                pasos_reales = len(ruta) - 1
                return {
                    "superficie": nombre_superficie,
                    "punto_inicio": ruta[0],
                    "punto_final": ruta[-1],
                    "paso_m": paso_m,
                    "pasos_ejecutados": pasos_reales,
                    "alcanzo_limite_pasos": pasos_reales >= tope,
                    "descenso_total": ruta[0]["z"] - ruta[-1]["z"],
                    "distancia_aproximada_m": pasos_reales * paso_m,
                    "ruta": ruta,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="punto_mas_bajo",
        description=(
            "Busca el punto de menor elevacion dentro de un circulo (x_centro, y_centro, "
            "radio_m) sobre una superficie, muestreando una malla cuadrada de paso "
            "resolucion_m y descartando los puntos fuera del circulo o fuera de la "
            "superficie. Util para localizar el punto de vertido/salida de una cuenca. "
            "LECCION: tope duro de 2500 puntos de malla; si radio_m/resolucion_m lo supera "
            "se devuelve error pidiendo subir resolucion_m o bajar radio_m, en vez de "
            "ejecutar una malla enorme de llamadas COM sin avisar."
        ),
    )
    async def punto_mas_bajo(
        nombre_superficie: str,
        x_centro: float,
        y_centro: float,
        radio_m: float,
        resolucion_m: float = 10.0,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                if resolucion_m <= 0 or radio_m <= 0:
                    return {"error": "radio_m y resolucion_m deben ser positivos."}

                n = int(math.ceil((2 * radio_m) / resolucion_m)) + 1
                total_estimado = n * n
                if total_estimado > 2500:
                    return {
                        "error": (
                            f"La malla resultante ({total_estimado} puntos) supera el tope "
                            f"de 2500. Sube resolucion_m o reduce radio_m."
                        )
                    }

                mejor = None
                evaluados = 0
                x0 = x_centro - radio_m
                y0 = y_centro - radio_m
                for i in range(n):
                    x = x0 + i * resolucion_m
                    if abs(x - x_centro) > radio_m:
                        continue
                    for j in range(n):
                        y = y0 + j * resolucion_m
                        dist = math.hypot(x - x_centro, y - y_centro)
                        if dist > radio_m:
                            continue
                        z = _elevacion_segura(surf, x, y)
                        if z is None:
                            continue
                        evaluados += 1
                        if mejor is None or z < mejor["z"]:
                            mejor = {"x": x, "y": y, "z": z}

                if mejor is None:
                    return {"error": "Ningun punto de la malla cayo dentro de la superficie."}
                return {
                    "superficie": nombre_superficie,
                    "centro": {"x": x_centro, "y": y_centro},
                    "radio_m": radio_m,
                    "resolucion_m": resolucion_m,
                    "puntos_evaluados": evaluados,
                    "punto_mas_bajo": mejor,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    register_cuenca(mcp, client, run_com)


def _delinear_cuenca_interna(
    surf,
    x_salida: float,
    y_salida: float,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    resolucion_m: float,
    max_pasos_por_traza: int,
    tolerancia_llegada_m: float,
    tope_puntos: int = 400,
):
    """Logica compartida por delinear_cuenca y area_cuenca: para cada celda de
    una malla sobre el bbox, traza el descenso D8 y comprueba si termina cerca
    del punto de salida. Devuelve (contribuyentes, evaluados, error|None)."""
    ancho = x_max - x_min
    alto = y_max - y_min
    if ancho <= 0 or alto <= 0:
        return None, 0, "El bounding box (x_min,y_min,x_max,y_max) es invalido."
    nx = int(math.ceil(ancho / resolucion_m)) + 1
    ny = int(math.ceil(alto / resolucion_m)) + 1
    total_estimado = nx * ny
    if total_estimado > tope_puntos:
        return None, 0, (
            f"La malla resultante ({total_estimado} puntos) supera el tope de "
            f"{tope_puntos}. Sube resolucion_m o reduce el bounding box."
        )

    contribuyentes = []
    evaluados = 0
    for i in range(nx):
        x = x_min + i * resolucion_m
        for j in range(ny):
            y = y_min + j * resolucion_m
            z = _elevacion_segura(surf, x, y)
            if z is None:
                continue
            evaluados += 1
            ruta = _trazar_descenso(surf, x, y, resolucion_m, max_pasos_por_traza)
            if not ruta:
                continue
            final = ruta[-1]
            if math.hypot(final["x"] - x_salida, final["y"] - y_salida) <= tolerancia_llegada_m:
                contribuyentes.append({"x": x, "y": y, "z": z})
    return contribuyentes, evaluados, None


def register_cuenca(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:
    """Registra delinear_cuenca y area_cuenca. Llamada desde register() para
    mantener el archivo legible (separa las tools de traza/punto-bajo de las
    de cuenca, que comparten _delinear_cuenca_interna)."""

    @mcp.tool(
        name="delinear_cuenca",
        description=(
            "Delineacion APROXIMADA de una cuenca vertiente a un punto de salida, por "
            "fuerza bruta: para cada celda de una malla sobre un bounding box "
            "(x_min,y_min,x_max,y_max) que TU debes acotar a la zona de interes real, "
            "traza el descenso D8 (ver trazar_flujo) y considera la celda parte de la "
            "cuenca si su traza termina a menos de tolerancia_llegada_m del punto de "
            "salida. NO es el algoritmo de delineacion de cuencas de Civil 3D/sacred "
            "(que opera sobre la TIN completa en memoria); es una aproximacion por "
            "muestreo, sensible a resolucion_m y a la eleccion del bounding box. "
            "LECCION: tope duro de 400 celdas de malla (cada celda dispara su propia "
            "traza D8, de hasta max_pasos_por_traza*8 llamadas COM: el coste total puede "
            "ser de varios miles de llamadas). Acota el bounding box a la cuenca "
            "esperada, no al proyecto completo."
        ),
    )
    async def delinear_cuenca(
        nombre_superficie: str,
        x_salida: float,
        y_salida: float,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        resolucion_m: float = 10.0,
        max_pasos_por_traza: int = 60,
        tolerancia_llegada_m: float | None = None,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                if resolucion_m <= 0:
                    return {"error": "resolucion_m debe ser positivo."}
                tol = tolerancia_llegada_m if tolerancia_llegada_m is not None else resolucion_m * 1.5

                contribuyentes, evaluados, error = _delinear_cuenca_interna(
                    surf, x_salida, y_salida, x_min, y_min, x_max, y_max,
                    resolucion_m, max(1, max_pasos_por_traza), tol,
                )
                if error:
                    return {"error": error}
                area_m2 = len(contribuyentes) * (resolucion_m ** 2)
                return {
                    "superficie": nombre_superficie,
                    "punto_salida": {"x": x_salida, "y": y_salida},
                    "resolucion_m": resolucion_m,
                    "tolerancia_llegada_m": tol,
                    "puntos_evaluados": evaluados,
                    "puntos_contribuyentes": len(contribuyentes),
                    "area_aproximada_m2": area_m2,
                    "area_aproximada_ha": area_m2 / 10000.0,
                    "puntos": contribuyentes,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="area_cuenca",
        description=(
            "Igual que delinear_cuenca (mismo algoritmo, mismas limitaciones y mismo tope "
            "de 400 celdas de malla) pero solo devuelve el resumen (area aproximada en m2 "
            "y ha, numero de puntos contribuyentes) sin la lista completa de puntos - "
            "usalo cuando solo necesites el area y quieras una respuesta mas ligera."
        ),
    )
    async def area_cuenca(
        nombre_superficie: str,
        x_salida: float,
        y_salida: float,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        resolucion_m: float = 10.0,
        max_pasos_por_traza: int = 60,
        tolerancia_llegada_m: float | None = None,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                if resolucion_m <= 0:
                    return {"error": "resolucion_m debe ser positivo."}
                tol = tolerancia_llegada_m if tolerancia_llegada_m is not None else resolucion_m * 1.5

                contribuyentes, evaluados, error = _delinear_cuenca_interna(
                    surf, x_salida, y_salida, x_min, y_min, x_max, y_max,
                    resolucion_m, max(1, max_pasos_por_traza), tol,
                )
                if error:
                    return {"error": error}
                area_m2 = len(contribuyentes) * (resolucion_m ** 2)
                return {
                    "superficie": nombre_superficie,
                    "punto_salida": {"x": x_salida, "y": y_salida},
                    "resolucion_m": resolucion_m,
                    "puntos_evaluados": evaluados,
                    "puntos_contribuyentes": len(contribuyentes),
                    "area_aproximada_m2": area_m2,
                    "area_aproximada_ha": area_m2 / 10000.0,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
