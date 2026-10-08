"""
tools_hidrologia_calculo.py  -  Hidrologia de calculo puro, sin dependencia de Civil 3D.

Formulas estandar de hidrologia superficial (Metodo Racional, Kirpich, retardo NRCS/SCS,
hidrograma triangular SCS). Ninguna toca la API de Civil 3D ni requiere el dibujo
abierto. Formulas verificadas contra fuentes tecnicas independientes (no traducidas del
proyecto civil3d_sacred, cuyo codigo de hidrologia mezcla objetos Civil3D con calculo
propio de forma dificil de aislar).

AVISO: son formulas de ESTIMACION RAPIDA de uso extendido en hidrologia superficial,
no sustituyen la normativa de drenaje aplicable en cada proyecto (en Espana, la
Instruccion 5.2-IC u otra normativa autonomica/local puede exigir un metodo distinto o
coeficientes especificos). Verificar siempre contra la normativa vigente antes de un
calculo de diseno definitivo.
"""
from __future__ import annotations
import logging
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP

log = logging.getLogger("civil3d_mcp.tools.hidrologia_calculo")


def register(mcp: FastMCP, client, run_com: Callable) -> None:

    @mcp.tool(
        name="estimar_escorrentia",
        description=(
            "Estima el caudal punta de escorrentia con el Metodo Racional clasico "
            "Q = C*I*A/360 (Q en m3/s, C adimensional 0-1, I en mm/h, A en hectareas). "
            "Estimacion rapida para cuencas pequenas (tipicamente <2-4 km2); no sustituye "
            "la normativa de drenaje aplicable (en Espana, Instruccion 5.2-IC u otra). "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def estimar_escorrentia(
        coeficiente_c: float,
        intensidad_mm_h: float,
        area_ha: float,
    ) -> dict[str, Any]:
        try:
            def _run():
                if not 0 <= coeficiente_c <= 1:
                    return {"error": "coeficiente_c debe estar entre 0 y 1."}
                caudal = coeficiente_c * intensidad_mm_h * area_ha / 360.0
                return {
                    "coeficiente_c": coeficiente_c,
                    "intensidad_mm_h": intensidad_mm_h,
                    "area_ha": area_ha,
                    "caudal_m3s": caudal,
                    "formula": "Q[m3/s] = C * I[mm/h] * A[ha] / 360",
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="tiempo_concentracion",
        description=(
            "Calcula el tiempo de concentracion de una cuenca por el metodo indicado. "
            "'kirpich': Tc[min] = 0.0195 * L[m]^0.77 * S[m/m]^-0.385 (formula metrica de "
            "Kirpich, cuencas pequenas con cauce definido). "
            "'nrcs': metodo de retardo NRCS/SCS, Tlag[h] = L[ft]^0.8*(S+1)^0.7/(1900*Y^0.5) "
            "con S=1000/CN-10 (retencion potencial en pulgadas), Y=pendiente media en %, "
            "Tc = Tlag/0.6 (requiere longitud, pendiente en % y curve number CN). "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def tiempo_concentracion(
        metodo: str,
        longitud_m: float,
        pendiente: float,
        curve_number: float | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        metodo : "kirpich" | "nrcs"
        longitud_m : float
            Longitud del cauce/flujo principal, en metros.
        pendiente : float
            Para "kirpich": pendiente media en m/m (ej. 0.02 = 2%).
            Para "nrcs": pendiente media en % (ej. 2.0 = 2%).
        curve_number : float, requerido solo para "nrcs"
            Numero de curva NRCS (CN), 30-98.
        """
        try:
            def _run():
                m = metodo.lower().strip()
                if m == "kirpich":
                    if pendiente <= 0:
                        return {"error": "pendiente debe ser > 0 (m/m) para Kirpich."}
                    tc_min = 0.0195 * (longitud_m ** 0.77) * (pendiente ** -0.385)
                    return {
                        "metodo": "kirpich",
                        "longitud_m": longitud_m,
                        "pendiente_m_m": pendiente,
                        "tc_minutos": tc_min,
                        "formula": "Tc[min] = 0.0195 * L[m]^0.77 * S[m/m]^-0.385",
                    }
                if m == "nrcs":
                    if curve_number is None:
                        return {"error": "curve_number es obligatorio para el metodo 'nrcs'."}
                    if not 30 <= curve_number <= 98:
                        return {"error": "curve_number fuera de rango tipico (30-98)."}
                    if pendiente <= 0:
                        return {"error": "pendiente debe ser > 0 (%) para NRCS."}
                    longitud_ft = longitud_m * 3.28084
                    s_pulgadas = 1000.0 / curve_number - 10.0
                    tlag_h = (
                        (longitud_ft ** 0.8) * ((s_pulgadas + 1) ** 0.7)
                        / (1900.0 * (pendiente ** 0.5))
                    )
                    tc_min = (tlag_h / 0.6) * 60.0
                    return {
                        "metodo": "nrcs",
                        "longitud_m": longitud_m,
                        "pendiente_pct": pendiente,
                        "curve_number": curve_number,
                        "retencion_potencial_in": s_pulgadas,
                        "lag_horas": tlag_h,
                        "tc_minutos": tc_min,
                        "formula": "Tlag[h]=L[ft]^0.8*(S+1)^0.7/(1900*Y[%]^0.5); Tc=Tlag/0.6",
                    }
                return {"error": f"Metodo '{metodo}' no reconocido. Usa 'kirpich' o 'nrcs'."}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="generar_hidrograma",
        description=(
            "Genera un hidrograma unitario sintetico triangular SCS a partir del area de "
            "la cuenca, la precipitacion efectiva (escorrentia) y el tiempo al pico. "
            "Qp[m3/s] = 0.208 * A[km2] * Q[mm] / Tp[h] (factor de pico SCS metrico, "
            "equivalente al 484 imperial); base del hidrograma Tb = 2.67*Tp (relacion "
            "estandar del hidrograma adimensional SCS, 3/8 del volumen antes del pico). "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def generar_hidrograma(
        area_km2: float,
        precipitacion_efectiva_mm: float,
        tiempo_pico_h: float,
    ) -> dict[str, Any]:
        try:
            def _run():
                if tiempo_pico_h <= 0:
                    return {"error": "tiempo_pico_h debe ser > 0."}
                qp = 0.208 * area_km2 * precipitacion_efectiva_mm / tiempo_pico_h
                tb = 2.67 * tiempo_pico_h
                return {
                    "area_km2": area_km2,
                    "precipitacion_efectiva_mm": precipitacion_efectiva_mm,
                    "tiempo_pico_h": tiempo_pico_h,
                    "caudal_pico_m3s": qp,
                    "tiempo_base_h": tb,
                    "puntos_hidrograma": [
                        {"tiempo_h": 0.0, "caudal_m3s": 0.0},
                        {"tiempo_h": tiempo_pico_h, "caudal_m3s": qp},
                        {"tiempo_h": tb, "caudal_m3s": 0.0},
                    ],
                    "formula": "Qp[m3/s] = 0.208 * A[km2] * Q[mm] / Tp[h]; Tb = 2.67*Tp",
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="dimensionar_cuenca_detencion",
        description=(
            "Estima el volumen de almacenamiento requerido en una cuenca de detencion "
            "dado un caudal de entrada (punta) y un caudal de salida maximo permitido, "
            "asumiendo un hidrograma de entrada TRIANGULAR SIMETRICO con base 2*Tc "
            "(Metodo Racional Modificado simplificado): Vs = Tc*(Qin-Qout)^2 / Qin. "
            "Es una aproximacion geometrica de estimacion rapida, NO un dimensionado "
            "final: el volumen real depende de la forma real del hietograma/hidrograma "
            "de entrada y de la duracion critica de tormenta, que este calculo no evalua. "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def dimensionar_cuenca_detencion(
        caudal_entrada_m3s: float,
        caudal_salida_m3s: float,
        tiempo_concentracion_min: float,
    ) -> dict[str, Any]:
        try:
            def _run():
                if caudal_salida_m3s >= caudal_entrada_m3s:
                    return {
                        "error": (
                            "caudal_salida_m3s debe ser menor que caudal_entrada_m3s "
                            "(si no, no hace falta laminar)."
                        )
                    }
                tc_seg = tiempo_concentracion_min * 60.0
                volumen = tc_seg * (caudal_entrada_m3s - caudal_salida_m3s) ** 2 / caudal_entrada_m3s
                return {
                    "caudal_entrada_m3s": caudal_entrada_m3s,
                    "caudal_salida_m3s": caudal_salida_m3s,
                    "tiempo_concentracion_min": tiempo_concentracion_min,
                    "volumen_estimado_m3": volumen,
                    "supuesto": "hidrograma de entrada triangular simetrico, base = 2*Tc",
                    "formula": "Vs[m3] = Tc[s] * (Qin-Qout)^2 / Qin",
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
