"""
tools_taludes.py  -  Geometria de taludes (catch-point / punto de encuentro
talud-terreno) sobre una TIN Surface via COM.
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError

log = logging.getLogger("civil3d_mcp.tools.taludes")


def _buscar_superficie(client: Civil3DClient, nombre: str):
    for surf in client._doc.Surfaces:
        if surf.Name == nombre:
            return surf
    return None


def _elevacion_segura(surf, x: float, y: float) -> float | None:
    try:
        return surf.FindElevationAtXY(x, y)
    except Exception:
        return None


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="calcular_geometria_talud",
        description=(
            "Calcula el punto de encuentro (catch point) entre un talud de pendiente "
            "constante y el terreno natural (superficie TIN), partiendo de un punto "
            "conocido (borde de plataforma/subrasante) y proyectando en una direccion "
            "(acimut) con una relacion horizontal:vertical dada. "
            "LECCION: no existe formula cerrada para esto (el terreno no es un plano), "
            "asi que se resuelve marchando a pasos de paso_busqueda_m a lo largo del "
            "acimut hasta detectar un cambio de signo entre la cota del talud y la cota "
            "del terreno (Surface.FindElevationAtXY), y luego se afina por biseccion. "
            "Tope duro de 500 pasos de marcha (cada paso es 1 llamada COM); si no "
            "encuentra corte devuelve error en vez de seguir buscando indefinidamente. "
            "acimut_grados sigue la convencion COGO del proyecto: grados desde el norte, "
            "sentido horario (0=norte, 90=este)."
        ),
    )
    async def calcular_geometria_talud(
        nombre_superficie: str,
        x_inicio: float,
        y_inicio: float,
        z_inicio: float,
        acimut_grados: float,
        relacion_h_v: float,
        sentido: str,
        distancia_maxima_m: float = 50.0,
        paso_busqueda_m: float = 1.0,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_superficie : str
            Nombre exacto de la superficie (terreno natural).
        x_inicio, y_inicio, z_inicio : float
            Punto de partida del talud (ej. borde de subrasante).
        acimut_grados : float
            Direccion de proyeccion del talud, en grados desde el norte, sentido horario.
        relacion_h_v : float
            Relacion horizontal:vertical del talud (ej. 2.0 para un talud 2:1).
        sentido : str
            "ascendente" si el talud sube al alejarse del punto de inicio (desmonte
            tipico), "descendente" si baja (terraplen tipico).
        distancia_maxima_m : float
            Distancia horizontal maxima a explorar antes de rendirse.
        paso_busqueda_m : float
            Paso de marcha para detectar el cambio de signo (minimo forzado: 0.1 m).
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                surf = _buscar_superficie(client, nombre_superficie)
                if surf is None:
                    return {"error": f"Superficie '{nombre_superficie}' no encontrada."}
                if relacion_h_v <= 0:
                    return {"error": "relacion_h_v debe ser positiva."}
                if sentido not in ("ascendente", "descendente"):
                    return {"error": "sentido debe ser 'ascendente' o 'descendente'."}

                signo = 1.0 if sentido == "ascendente" else -1.0
                pendiente_v_por_h = signo / relacion_h_v
                acimut_rad = math.radians(acimut_grados)
                ux, uy = math.sin(acimut_rad), math.cos(acimut_rad)

                def z_talud(d: float) -> float:
                    return z_inicio + pendiente_v_por_h * d

                def diferencia(d: float):
                    x = x_inicio + ux * d
                    y = y_inicio + uy * d
                    zt = _elevacion_segura(surf, x, y)
                    if zt is None:
                        return None
                    return z_talud(d) - zt

                paso = max(0.1, paso_busqueda_m)
                tope_pasos = min(int(distancia_maxima_m / paso) + 1, 500)

                diff_prev = diferencia(0.0)
                if diff_prev is None:
                    return {"error": "El punto de inicio esta fuera de la superficie."}

                d_prev = 0.0
                d = paso
                corte = None
                for _ in range(tope_pasos):
                    diff = diferencia(d)
                    if diff is not None and diff_prev is not None and diff_prev * diff <= 0:
                        lo, hi = d_prev, d
                        f_lo = diff_prev
                        for _ in range(40):
                            mid = (lo + hi) / 2.0
                            f_mid = diferencia(mid)
                            if f_mid is None:
                                break
                            if f_lo * f_mid <= 0:
                                hi = mid
                            else:
                                lo = mid
                                f_lo = f_mid
                        corte = hi
                        break
                    if diff is not None:
                        diff_prev = diff
                        d_prev = d
                    d += paso

                if corte is None:
                    return {
                        "error": (
                            f"No se encontro punto de corte con el terreno dentro de "
                            f"{distancia_maxima_m} m. Prueba a aumentar distancia_maxima_m "
                            f"o revisa sentido/relacion_h_v."
                        )
                    }

                x_final = x_inicio + ux * corte
                y_final = y_inicio + uy * corte
                z_final = z_talud(corte)
                return {
                    "superficie": nombre_superficie,
                    "punto_inicio": {"x": x_inicio, "y": y_inicio, "z": z_inicio},
                    "acimut_grados": acimut_grados,
                    "relacion_h_v": relacion_h_v,
                    "sentido": sentido,
                    "distancia_horizontal_m": corte,
                    "punto_corte": {"x": x_final, "y": y_final, "z": z_final},
                    "altura_talud_m": abs(z_final - z_inicio),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
