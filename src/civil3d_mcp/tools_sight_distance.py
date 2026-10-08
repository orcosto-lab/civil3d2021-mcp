"""
tools_sight_distance.py  -  Distancias de visibilidad AASHTO, calculo puro.

Formula de distancia de parada (SSD) verificada: es la formula fisica estandar del
Green Book de AASHTO (deceleracion + reaccion), deducible de primeros principios, no
una tabla. La distancia de adelantamiento (PSD) SI es una tabla empirica del Green Book
(no una formula cerrada): se usa la tabla metrica publicada (AASHTO Green Book 2011,
Tabla de PSD minima para autovias de 2 carriles) con interpolacion lineal entre puntos.

LECCION: la distancia de decision (DSD) de AASHTO tambien es tabla empirica (Tabla 3-3
del Green Book, por maniobra A-E y velocidad), pero no se ha podido verificar con
confianza suficiente el valor exacto de cada celda contra una fuente fiable durante el
desarrollo de esta tool - por eso NO esta implementada aqui (ver accion "decision" mas
abajo, que devuelve un aviso en vez de un numero inventado). Si se necesita, verificar
directamente en la edicion vigente del AASHTO Green Book antes de implementarla.

AVISO ADICIONAL: estas formulas son de AASHTO (normativa de EEUU). Si el proyecto es en
Espana, la normativa aplicable para distancias de visibilidad y parada es la Instruccion
de Carreteras 3.1-IC (Trazado), que usa formulas y valores distintos - no asumir que
AASHTO es la referencia correcta sin confirmarlo con Pedro.
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP

log = logging.getLogger("civil3d_mcp.tools.sight_distance")

# AASHTO Green Book 2011 - PSD minima para autovias de 2 carriles, metrica.
# (velocidad_kmh, psd_metros)
_TABLA_PSD_AASHTO = [
    (50, 160), (60, 180), (70, 210), (80, 245),
    (90, 280), (100, 320), (110, 355), (120, 395),
]


def _interpolar_psd(velocidad_kmh: float) -> dict[str, Any]:
    tabla = _TABLA_PSD_AASHTO
    if velocidad_kmh <= tabla[0][0]:
        return {"psd_metros": tabla[0][1], "extrapolado": velocidad_kmh < tabla[0][0]}
    if velocidad_kmh >= tabla[-1][0]:
        return {"psd_metros": tabla[-1][1], "extrapolado": velocidad_kmh > tabla[-1][0]}
    for (v0, d0), (v1, d1) in zip(tabla, tabla[1:]):
        if v0 <= velocidad_kmh <= v1:
            frac = (velocidad_kmh - v0) / (v1 - v0)
            return {"psd_metros": d0 + frac * (d1 - d0), "extrapolado": False}
    return {"psd_metros": None, "extrapolado": True}


def register(mcp: FastMCP, client, run_com: Callable) -> None:

    @mcp.tool(
        name="distancia_visibilidad",
        description=(
            "Calcula distancia de visibilidad segun AASHTO (normativa EEUU - ver aviso "
            "de normativa espanola en el modulo). tipo='parada' (SSD): formula fisica "
            "SSD[m] = 0.278*V*t + V^2/(254*(f+G)), V en km/h, t=tiempo de percepcion-"
            "reaccion (2.5 s AASHTO), f=coeficiente de rozamiento, G=pendiente en tanto "
            "por uno (+ = subida). tipo='adelantamiento' (PSD): tabla metrica AASHTO "
            "Green Book 2011 con interpolacion lineal (rango 50-120 km/h, fuera de rango "
            "se extrapola al extremo mas cercano con aviso). tipo='decision' (DSD): NO "
            "IMPLEMENTADA, ver LECCION en el modulo - devuelve error explicativo en vez "
            "de un numero sin verificar. Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def distancia_visibilidad(
        tipo: str,
        velocidad_kmh: float,
        coeficiente_rozamiento: float | None = None,
        pendiente: float = 0.0,
        tiempo_reaccion_s: float = 2.5,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        tipo : "parada" | "adelantamiento" | "decision"
        velocidad_kmh : float
            Velocidad de diseno o de circulacion, en km/h.
        coeficiente_rozamiento : float, requerido solo para tipo="parada"
            Coeficiente de rozamiento longitudinal rueda-pavimento (tipicamente 0.28-0.40
            segun velocidad; AASHTO lo tabula por velocidad, aqui se pide explicito para
            no hardcodear una tabla adicional sin verificar).
        pendiente : float
            Pendiente longitudinal en tanto por uno (0.02 = 2% subida, -0.02 = 2% bajada).
            Solo aplica a tipo="parada".
        tiempo_reaccion_s : float
            Tiempo de percepcion-reaccion, por defecto 2.5 s (valor AASHTO estandar).
        """
        try:
            def _run():
                t = tipo.lower().strip()
                if t == "parada":
                    if coeficiente_rozamiento is None:
                        return {
                            "error": (
                                "coeficiente_rozamiento es obligatorio para tipo='parada' "
                                "(AASHTO lo tabula por velocidad; aqui se pide explicito)."
                            )
                        }
                    f = coeficiente_rozamiento
                    v = velocidad_kmh
                    distancia_reaccion = 0.278 * v * tiempo_reaccion_s
                    distancia_frenado = v ** 2 / (254 * (f + pendiente))
                    ssd = distancia_reaccion + distancia_frenado
                    return {
                        "tipo": "parada",
                        "velocidad_kmh": v,
                        "distancia_reaccion_m": distancia_reaccion,
                        "distancia_frenado_m": distancia_frenado,
                        "ssd_metros": ssd,
                        "formula": "SSD[m] = 0.278*V*t + V^2/(254*(f+G))",
                        "fuente": "AASHTO Green Book (formula fisica, no tabla)",
                    }
                if t == "adelantamiento":
                    r = _interpolar_psd(velocidad_kmh)
                    return {
                        "tipo": "adelantamiento",
                        "velocidad_kmh": velocidad_kmh,
                        "psd_metros": r["psd_metros"],
                        "fuera_de_tabla": r["extrapolado"],
                        "fuente": "AASHTO Green Book 2011, tabla metrica PSD 2 carriles (50-120 km/h)",
                    }
                if t == "decision":
                    return {
                        "error": (
                            "distancia de decision (DSD) no implementada: no se pudo "
                            "verificar con confianza suficiente la Tabla 3-3 del AASHTO "
                            "Green Book durante el desarrollo de esta tool. Consultar la "
                            "edicion vigente del Green Book directamente."
                        )
                    }
                return {
                    "error": f"tipo '{tipo}' no reconocido. Usa 'parada', 'adelantamiento' o 'decision'."
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
