"""
tools_cogo_calculo.py  -  Calculo COGO clasico (topografia), sin dependencia de Civil 3D.

Todas las tools de este modulo son matematica pura (trigonometria de poligonales y
curvas circulares); no necesitan el dibujo abierto ni tocan la API COM. Se mantienen
en el mismo patron async+register(mcp, client, run_com) que el resto del proyecto por
consistencia, aunque run_com aqui solo ejecuta calculo en el hilo COM compartido, no
COM real.

Convencion de acimut: grados sexagesimales, medidos en el sentido horario desde el
Norte (0 = Norte, 90 = Este, 180 = Sur, 270 = Oeste) - convencion topografica estandar,
NO la convencion matematica de AutoCAD (0 = Este, antihorario).
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable
from mcp.server.fastmcp import FastMCP

log = logging.getLogger("civil3d_mcp.tools.cogo_calculo")


def _rumbo_desde_acimut(acimut_grados: float) -> str:
    """Convierte un acimut (0-360, horario desde N) a rumbo de cuadrante N/S xx W/E."""
    a = acimut_grados % 360
    if a <= 90:
        return f"N {a:.4f} E"
    if a <= 180:
        return f"S {180 - a:.4f} E"
    if a <= 270:
        return f"S {a - 180:.4f} W"
    return f"N {360 - a:.4f} W"


def register(mcp: FastMCP, client, run_com: Callable) -> None:

    @mcp.tool(
        name="inversa_cogo",
        description=(
            "Calcula distancia y acimut entre dos puntos (X1,Y1) -> (X2,Y2). Operacion "
            "COGO clasica 'inversa'. Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def inversa_cogo(x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
        try:
            def _run():
                de = x2 - x1
                dn = y2 - y1
                distancia = math.hypot(de, dn)
                acimut = math.degrees(math.atan2(de, dn)) % 360
                return {
                    "punto_1": {"x": x1, "y": y1},
                    "punto_2": {"x": x2, "y": y2},
                    "delta_x": de,
                    "delta_y": dn,
                    "distancia": distancia,
                    "acimut_grados": acimut,
                    "rumbo": _rumbo_desde_acimut(acimut),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="radiacion_cogo",
        description=(
            "Operacion COGO clasica 'radiacion': proyecta un punto desde (X,Y) dado un "
            "acimut y una distancia (con pendiente opcional para obtener tambien Z). "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def radiacion_cogo(
        x: float,
        y: float,
        acimut_grados: float,
        distancia: float,
        z: float | None = None,
        pendiente_pct: float | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        pendiente_pct : float, opcional
            Pendiente en % (positiva = subida) a lo largo del tramo. Solo se aplica si
            se indica tambien z (cota de origen); si no, se ignora.
        """
        try:
            def _run():
                acimut_rad = math.radians(acimut_grados)
                x2 = x + distancia * math.sin(acimut_rad)
                y2 = y + distancia * math.cos(acimut_rad)
                resultado: dict[str, Any] = {
                    "origen": {"x": x, "y": y},
                    "acimut_grados": acimut_grados % 360,
                    "distancia": distancia,
                    "destino": {"x": x2, "y": y2},
                }
                if z is not None:
                    if pendiente_pct is not None:
                        z2 = z + distancia * (pendiente_pct / 100.0)
                        resultado["destino"]["z"] = z2
                    else:
                        resultado["destino"]["z"] = z
                return resultado
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="poligonal_cogo",
        description=(
            "Resuelve una poligonal (traverse) a partir de un punto de arranque y una "
            "lista ordenada de tramos {acimut_grados, distancia}. Si cerrar=true, asume "
            "que el ultimo tramo deberia volver al punto de arranque y calcula el error "
            "de cierre (no ajusta la poligonal, solo informa del error). "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def poligonal_cogo(
        x_inicio: float,
        y_inicio: float,
        tramos: list[dict[str, float]],
        cerrar: bool = False,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        tramos : list of {"acimut_grados": float, "distancia": float}
            Tramos en orden. Cada uno se aplica desde el vertice anterior.
        cerrar : bool
            Si true, compara el ultimo vertice contra (x_inicio, y_inicio) y devuelve
            el error de cierre lineal y la precision (error / longitud total).
        """
        try:
            def _run():
                if not tramos:
                    return {"error": "La lista de tramos no puede estar vacia."}
                x, y = x_inicio, y_inicio
                vertices = [{"indice": 0, "x": x, "y": y}]
                longitud_total = 0.0
                for i, tramo in enumerate(tramos, start=1):
                    acimut_rad = math.radians(tramo["acimut_grados"])
                    dist = tramo["distancia"]
                    x += dist * math.sin(acimut_rad)
                    y += dist * math.cos(acimut_rad)
                    longitud_total += dist
                    vertices.append({"indice": i, "x": x, "y": y})
                resultado: dict[str, Any] = {
                    "vertices": vertices,
                    "longitud_total": longitud_total,
                    "vertice_final": {"x": x, "y": y},
                }
                if cerrar:
                    error_x = x - x_inicio
                    error_y = y - y_inicio
                    error_lineal = math.hypot(error_x, error_y)
                    resultado["cierre"] = {
                        "error_x": error_x,
                        "error_y": error_y,
                        "error_lineal": error_lineal,
                        "precision": (
                            f"1:{longitud_total / error_lineal:.0f}"
                            if error_lineal > 0 else "exacto"
                        ),
                    }
                return resultado
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="resolver_curva",
        description=(
            "Resuelve una curva circular horizontal a partir de 2 de sus 5 elementos "
            "conocidos: radio, delta_grados (angulo central), longitud (arco), tangente "
            "o cuerda. Completa los 3 restantes. Formulas estandar de geometria de "
            "curva circular (L=R*delta, T=R*tan(delta/2), C=2*R*sin(delta/2)); las "
            "combinaciones longitud+tangente y longitud+cuerda no tienen solucion "
            "algebraica cerrada y se resuelven por biseccion numerica. "
            "Calculo puro, no requiere Civil 3D abierto."
        ),
    )
    async def resolver_curva(
        radio: float | None = None,
        delta_grados: float | None = None,
        longitud: float | None = None,
        tangente: float | None = None,
        cuerda: float | None = None,
    ) -> dict[str, Any]:
        try:
            def _run():
                conocidos = {
                    "radio": radio, "delta_grados": delta_grados, "longitud": longitud,
                    "tangente": tangente, "cuerda": cuerda,
                }
                dados = {k: v for k, v in conocidos.items() if v is not None}
                if len(dados) != 2:
                    return {
                        "error": (
                            f"Se requieren exactamente 2 elementos conocidos, se "
                            f"recibieron {len(dados)}: {list(dados.keys())}"
                        )
                    }
                try:
                    r, d = _radio_delta_desde_dos(radio, delta_grados, longitud, tangente, cuerda)
                except ValueError as exc:
                    return {"error": str(exc)}
                return {
                    "radio": r,
                    "delta_grados": math.degrees(d),
                    "longitud": r * d,
                    "tangente": r * math.tan(d / 2),
                    "cuerda": 2 * r * math.sin(d / 2),
                    "externa": r * (1 / math.cos(d / 2) - 1),
                    "flecha": r * (1 - math.cos(d / 2)),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


def _biseccion(f, lo: float, hi: float, iteraciones: int = 100) -> float:
    """Biseccion simple; asume f(lo) y f(hi) de signo opuesto."""
    flo = f(lo)
    for _ in range(iteraciones):
        mid = (lo + hi) / 2
        fmid = f(mid)
        if flo * fmid <= 0:
            hi = mid
        else:
            lo, flo = mid, fmid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2


def _radio_delta_desde_dos(
    radio: float | None,
    delta_grados: float | None,
    longitud: float | None,
    tangente: float | None,
    cuerda: float | None,
) -> tuple[float, float]:
    """
    Deriva (radio, delta_en_radianes) a partir de exactamente 2 elementos conocidos
    de la curva. Lanza ValueError si la combinacion no tiene solucion soportada.
    """
    d = math.radians(delta_grados) if delta_grados is not None else None
    r = radio

    if r is not None and d is not None:
        return r, d
    if r is not None and longitud is not None:
        return r, longitud / r
    if r is not None and tangente is not None:
        return r, 2 * math.atan(tangente / r)
    if r is not None and cuerda is not None:
        if abs(cuerda) > 2 * r:
            raise ValueError("La cuerda no puede ser mayor que el diametro (2*radio).")
        return r, 2 * math.asin(cuerda / (2 * r))
    if d is not None and longitud is not None:
        return longitud / d, d
    if d is not None and tangente is not None:
        return tangente / math.tan(d / 2), d
    if d is not None and cuerda is not None:
        return cuerda / (2 * math.sin(d / 2)), d
    if tangente is not None and cuerda is not None:
        # tangente/cuerda = tan(d/2) / (2*sin(d/2)) = 1 / (2*cos(d/2))
        cociente = cuerda / (2 * tangente)
        if not -1 <= cociente <= 1:
            raise ValueError("Combinacion tangente+cuerda geometricamente imposible.")
        d = 2 * math.acos(cociente)
        return tangente / math.tan(d / 2), d
    if longitud is not None and tangente is not None:
        # tan(d/2) - tangente*d/longitud = 0, raiz en (0, pi)
        f = lambda dd: math.tan(dd / 2) - tangente * dd / longitud
        d = _biseccion(f, 1e-6, math.pi - 1e-6)
        return longitud / d, d
    if longitud is not None and cuerda is not None:
        # sin(d/2) - cuerda*d/(2*longitud) = 0, raiz en (0, pi)
        f = lambda dd: math.sin(dd / 2) - cuerda * dd / (2 * longitud)
        d = _biseccion(f, 1e-6, math.pi - 1e-6)
        return longitud / d, d
    raise ValueError("Combinacion de 2 elementos no soportada.")
