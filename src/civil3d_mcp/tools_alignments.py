"""
tools_alignments.py  -  Herramientas para alineaciones de Civil 3D
"""
from __future__ import annotations
import logging
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, Civil3DError, iter_com_collection, variant_out_double

log = logging.getLogger("civil3d_mcp.tools.alignments")


def _buscar_alineacion(client: Civil3DClient, nombre: str):
    """Busca una alineacion por nombre exacto en AlignmentsSiteless. None si no existe."""
    for alig in iter_com_collection(client._doc.AlignmentsSiteless):
        if alig.Name == nombre:
            return alig
    return None


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="list_alignments",
        description="Lista todas las alineaciones del dibujo con nombre, longitud y PK inicial/final.",
    )
    async def list_alignments() -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                resultado = []
                for alig in iter_com_collection(client._doc.AlignmentsSiteless):
                    info = {
                        "nombre": alig.Name,
                        "descripcion": alig.Description,
                        "longitud": alig.Length,
                        "pk_inicio": alig.StartingStation,
                        "pk_fin": alig.EndingStation,
                    }
                    resultado.append(info)
                return {"total": len(resultado), "alineaciones": resultado}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="coordenadas_en_pk",
        description="Obtiene las coordenadas X,Y de una alineacion en un PK (estacionamiento) dado.",
    )
    async def coordenadas_en_pk(
        nombre_alineacion: str,
        pk: float,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        pk : float
            Estacionamiento (PK) en metros.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                x = alig.GetXAtStation(pk)
                y = alig.GetYAtStation(pk)
                return {
                    "alineacion": nombre_alineacion,
                    "pk": pk,
                    "x": x,
                    "y": y,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="pk_en_punto",
        description=(
            "Operacion inversa de coordenadas_en_pk: dado un punto X,Y, calcula el PK "
            "(estacionamiento) y el offset (desplazamiento lateral, signo segun lado del "
            "eje) respecto a una alineacion. "
            "LECCION: usa Alignment.StationOffset con parametros COM por referencia "
            "(VARIANT VT_R8|VT_BYREF via variant_out_double()); un float normal de Python "
            "es inmutable y Civil 3D no puede escribir el resultado en el. Lanza error si "
            "el punto queda fuera del rango de la alineacion (PointNotOnEntityException)."
        ),
    )
    async def pk_en_punto(
        nombre_alineacion: str,
        x: float,
        y: float,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        x : float
            Coordenada Este del punto.
        y : float
            Coordenada Norte del punto.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                pk_var = variant_out_double()
                offset_var = variant_out_double()
                try:
                    alig.StationOffset(x, y, pk_var, offset_var)
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo calcular PK/offset (punto probablemente fuera "
                            f"del rango de la alineacion): {exc}"
                        )
                    }
                return {
                    "alineacion": nombre_alineacion,
                    "x": x,
                    "y": y,
                    "pk": float(pk_var.value),
                    "offset": float(offset_var.value),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="listar_perfiles",
        description=(
            "Lista los perfiles (rasantes) asociados a una alineacion: nombre, tipo, "
            "estilo y rango de elevaciones/PK. "
            "NO PROBADA: propiedades tomadas de la API .NET de Civil 3D (Profile class, "
            "verificadas en docs oficiales), pendiente de confirmar que el objeto COM "
            "expuesto via AeccXUiLand.AeccApplication use los mismos nombres."
        ),
    )
    async def listar_perfiles(nombre_alineacion: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                resultado = []
                for perfil in iter_com_collection(alig.Profiles):
                    info: dict[str, Any] = {"nombre": perfil.Name}
                    for attr, clave in (
                        ("Description", "descripcion"),
                        ("ProfileType", "tipo"),
                        ("StyleName", "estilo"),
                        ("ElevationMin", "elevacion_min"),
                        ("ElevationMax", "elevacion_max"),
                        ("StartingStation", "pk_inicio"),
                        ("EndingStation", "pk_fin"),
                    ):
                        try:
                            info[clave] = getattr(perfil, attr)
                        except Exception:
                            pass
                    resultado.append(info)
                return {
                    "alineacion": nombre_alineacion,
                    "total": len(resultado),
                    "perfiles": resultado,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="info_perfil",
        description=(
            "Informacion detallada de un perfil concreto de una alineacion: tipo, estilo, "
            "rango de elevaciones/PK y, si se indica pk, la elevacion en ese punto "
            "(Profile.ElevationAt). "
            "NO PROBADA: mismas reservas que listar_perfiles sobre nombres de propiedad "
            "COM sin verificar contra un dibujo real."
        ),
    )
    async def info_perfil(
        nombre_alineacion: str,
        nombre_perfil: str,
        pk: float | None = None,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                perfil = None
                for p in iter_com_collection(alig.Profiles):
                    if p.Name == nombre_perfil:
                        perfil = p
                        break
                if perfil is None:
                    return {
                        "error": f"Perfil '{nombre_perfil}' no encontrado en '{nombre_alineacion}'."
                    }
                info: dict[str, Any] = {
                    "alineacion": nombre_alineacion,
                    "nombre": perfil.Name,
                }
                for attr, clave in (
                    ("Description", "descripcion"),
                    ("ProfileType", "tipo"),
                    ("StyleName", "estilo"),
                    ("ElevationMin", "elevacion_min"),
                    ("ElevationMax", "elevacion_max"),
                    ("StartingStation", "pk_inicio"),
                    ("EndingStation", "pk_fin"),
                    ("Length", "longitud"),
                ):
                    try:
                        info[clave] = getattr(perfil, attr)
                    except Exception:
                        pass
                if pk is not None:
                    try:
                        info["elevacion_en_pk"] = perfil.ElevationAt(pk)
                        info["pk_consultado"] = pk
                    except Exception as exc:
                        info["elevacion_en_pk_error"] = str(exc)
                return info
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="verificar_valor_k",
        description=(
            "Calcula el valor K (=longitud/diferencia algebraica de pendientes) de una "
            "curva vertical y lo compara contra un K minimo que TU debes indicar segun "
            "la normativa aplicable a tu proyecto. "
            "LECCION: no hay tabla de K minimos AASHTO ni de la Instruccion de Carreteras "
            "espanola 3.1-IC hardcodeada aqui a proposito - no se pudo verificar con "
            "confianza suficiente ninguna de las dos tablas durante el desarrollo, y "
            "ademas dependen de la normativa de cada proyecto (AASHTO en EEUU, 3.1-IC en "
            "Espana, con valores distintos). Esta tool solo hace la aritmetica (K=L/A) y "
            "la comparacion; el K minimo correcto lo aportas tu desde tu referencia. "
            "No lee la curva directamente del perfil via COM (no verificado); pasa "
            "longitud y diferencia de pendientes ya conocidas (ej. de `info_perfil` "
            "leyendo pendientes en PKs a ambos lados de la curva)."
        ),
    )
    async def verificar_valor_k(
        longitud_m: float,
        diferencia_algebraica_pct: float,
        k_minimo: float,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        longitud_m : float
            Longitud de la curva vertical, en metros.
        diferencia_algebraica_pct : float
            Diferencia algebraica de pendientes (A = pendiente_salida - pendiente_entrada),
            en puntos porcentuales (ej. si pasa de -2% a +3%, A = 5).
        k_minimo : float
            K minimo exigido por la normativa que estes aplicando (tu lo aportas).
        """
        try:
            def _run():
                if diferencia_algebraica_pct == 0:
                    return {"error": "diferencia_algebraica_pct no puede ser 0 (no hay curva)."}
                k_real = longitud_m / abs(diferencia_algebraica_pct)
                cumple = k_real >= k_minimo
                return {
                    "longitud_m": longitud_m,
                    "diferencia_algebraica_pct": diferencia_algebraica_pct,
                    "k_real": k_real,
                    "k_minimo": k_minimo,
                    "cumple": cumple,
                    "tipo_curva": "convexa (cresta)" if diferencia_algebraica_pct < 0 else "concava (acuerdo)",
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="punto_en_pk_offset",
        description=(
            "Calcula las coordenadas X,Y de un punto definido por PK (estacionamiento) y "
            "offset (desplazamiento lateral; positivo=derecha, negativo=izquierda segun "
            "sentido de avance) respecto a una alineacion. Es la operacion inversa de "
            "pk_en_punto, y mas general que coordenadas_en_pk porque admite offset != 0. "
            "LECCION: usa Alignment.PointLocation(pk, offset, ByRef este, ByRef norte) con "
            "VARIANT VT_R8|VT_BYREF via variant_out_double() (API confirmada en docs "
            "oficiales de Autodesk). Lanza error si el PK+offset caen fuera del rango "
            "valido de la alineacion."
        ),
    )
    async def punto_en_pk_offset(
        nombre_alineacion: str,
        pk: float,
        offset: float = 0.0,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        pk : float
            Estacionamiento (PK) en metros.
        offset : float
            Desplazamiento lateral en metros (positivo=derecha, negativo=izquierda).
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                x_var = variant_out_double()
                y_var = variant_out_double()
                try:
                    alig.PointLocation(pk, offset, x_var, y_var)
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo calcular el punto (PK/offset probablemente fuera "
                            f"del rango de la alineacion): {exc}"
                        )
                    }
                return {
                    "alineacion": nombre_alineacion,
                    "pk": pk,
                    "offset": offset,
                    "x": float(x_var.value),
                    "y": float(y_var.value),
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="verificar_perfil",
        description=(
            "Verifica la pendiente maxima de un perfil (rasante) mediante muestreo "
            "numerico: calcula Profile.ElevationAt en PKs sucesivos (paso "
            "intervalo_muestreo_m) y obtiene la pendiente entre cada par de muestras "
            "consecutivas. Devuelve la pendiente maxima/minima encontrada y los tramos "
            "donde se supera pendiente_maxima_pct. "
            "LECCION: no lee las entidades del perfil (ProfileTangent/ProfileParabola) "
            "porque esa estructura COM no esta verificada contra un dibujo real; el "
            "muestreo numerico es mas lento pero solo depende de ElevationAt, que si esta "
            "confirmada en la documentacion oficial de Autodesk. Un intervalo demasiado "
            "pequeno en perfiles largos genera muchas llamadas COM (una por muestra): usa "
            "un intervalo razonable (ej. 5-20 m) segun la longitud del perfil."
        ),
    )
    async def verificar_perfil(
        nombre_alineacion: str,
        nombre_perfil: str,
        pendiente_maxima_pct: float,
        intervalo_muestreo_m: float = 10.0,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        nombre_perfil : str
            Nombre exacto del perfil dentro de esa alineacion.
        pendiente_maxima_pct : float
            Pendiente maxima admitida, en valor absoluto (%).
        intervalo_muestreo_m : float
            Paso de muestreo en PK, en metros. Minimo forzado: 1.0 m.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                perfil = None
                for p in iter_com_collection(alig.Profiles):
                    if p.Name == nombre_perfil:
                        perfil = p
                        break
                if perfil is None:
                    return {
                        "error": f"Perfil '{nombre_perfil}' no encontrado en '{nombre_alineacion}'."
                    }
                paso = max(1.0, intervalo_muestreo_m)
                pk_ini = perfil.StartingStation
                pk_fin = perfil.EndingStation
                if pk_fin <= pk_ini:
                    return {"error": "Rango de PK del perfil invalido (fin <= inicio)."}

                muestras = []
                pk = pk_ini
                while pk <= pk_fin:
                    try:
                        muestras.append((pk, perfil.ElevationAt(pk)))
                    except Exception:
                        pass
                    pk += paso
                if pk_fin not in [m[0] for m in muestras]:
                    try:
                        muestras.append((pk_fin, perfil.ElevationAt(pk_fin)))
                    except Exception:
                        pass

                if len(muestras) < 2:
                    return {"error": "No se obtuvieron suficientes muestras de elevacion."}

                tramos_excedidos = []
                pendiente_max_encontrada = 0.0
                pendiente_min_encontrada = 0.0
                for (pk_a, z_a), (pk_b, z_b) in zip(muestras, muestras[1:]):
                    dist = pk_b - pk_a
                    if dist <= 0:
                        continue
                    pendiente_pct = (z_b - z_a) / dist * 100.0
                    pendiente_max_encontrada = max(pendiente_max_encontrada, pendiente_pct)
                    pendiente_min_encontrada = min(pendiente_min_encontrada, pendiente_pct)
                    if abs(pendiente_pct) > pendiente_maxima_pct:
                        tramos_excedidos.append({
                            "pk_inicio": pk_a,
                            "pk_fin": pk_b,
                            "pendiente_pct": pendiente_pct,
                        })

                return {
                    "alineacion": nombre_alineacion,
                    "perfil": nombre_perfil,
                    "intervalo_muestreo_m": paso,
                    "total_muestras": len(muestras),
                    "pendiente_maxima_admitida_pct": pendiente_maxima_pct,
                    "pendiente_maxima_encontrada_pct": pendiente_max_encontrada,
                    "pendiente_minima_encontrada_pct": pendiente_min_encontrada,
                    "cumple": len(tramos_excedidos) == 0,
                    "tramos_que_exceden": tramos_excedidos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="verificar_alineacion",
        description=(
            "Recorre las entidades geometricas de una alineacion (Alignment.Entities: "
            "tangentes, curvas circulares, clotoides) y verifica que las curvas circulares "
            "cumplan un radio minimo (obligatorio) y, opcionalmente, una longitud minima. "
            "El radio/longitud minimos los aportas tu segun la normativa de tu proyecto "
            "(no hay tabla AASHTO/3.1-IC hardcodeada, igual que en verificar_valor_k). "
            "LECCION: solo AlignmentArc expone la propiedad Radius (confirmado en docs "
            "oficiales de Autodesk); las tangentes (AlignmentLine) y clotoides "
            "(AlignmentSpiral) no la tienen. Se detecta el tipo de entidad intentando leer "
            ".Radius y capturando el error si no existe, en vez de comparar contra un "
            "enum EntityType sin verificar. Las clotoides se listan pero no se verifican "
            "(su geometria no es de radio constante)."
        ),
    )
    async def verificar_alineacion(
        nombre_alineacion: str,
        radio_minimo: float,
        longitud_minima_curva: float | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        radio_minimo : float
            Radio minimo admitido para curvas circulares, en metros.
        longitud_minima_curva : float, opcional
            Longitud minima admitida para curvas circulares, en metros.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}

                curvas = []
                clotoides = []
                tangentes = 0
                incumplimientos = []

                for ent in iter_com_collection(alig.Entities):
                    try:
                        radio = ent.Radius
                    except Exception:
                        radio = None

                    if radio is not None:
                        try:
                            longitud = ent.ArcLength
                        except Exception:
                            try:
                                longitud = ent.EndingStation - ent.StartingStation
                            except Exception:
                                longitud = None
                        info = {"radio": radio, "longitud": longitud}
                        try:
                            info["pk_inicio"] = ent.StartingStation
                            info["pk_fin"] = ent.EndingStation
                        except Exception:
                            pass
                        curvas.append(info)

                        problemas = []
                        if radio < radio_minimo:
                            problemas.append(f"radio {radio:.3f} < minimo {radio_minimo}")
                        if (
                            longitud_minima_curva is not None
                            and longitud is not None
                            and longitud < longitud_minima_curva
                        ):
                            problemas.append(
                                f"longitud {longitud:.3f} < minima {longitud_minima_curva}"
                            )
                        if problemas:
                            incumplimientos.append({**info, "problemas": problemas})
                        continue

                    try:
                        _ = ent.RadiusIn
                        clotoides.append(True)
                        continue
                    except Exception:
                        pass

                    tangentes += 1

                return {
                    "alineacion": nombre_alineacion,
                    "radio_minimo": radio_minimo,
                    "longitud_minima_curva": longitud_minima_curva,
                    "total_tangentes": tangentes,
                    "total_curvas_circulares": len(curvas),
                    "total_clotoides": len(clotoides),
                    "curvas": curvas,
                    "cumple": len(incumplimientos) == 0,
                    "incumplimientos": incumplimientos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="crear_alineacion_vacia",
        description=(
            "Crea una alineacion vacia (sin geometria) en la coleccion de alineaciones "
            "sin site (AlignmentsSiteless). Para darle geometria hay que usar "
            "`crear_alineacion_desde_polilinea` o editarla desde la interfaz de Civil3D "
            "(la edicion por tramos - anadir tangentes/curvas una a una - no esta "
            "confirmada como alcanzable via la API COM/ActiveX legacy que usa este "
            "proyecto: la documentacion oficial solo confirma esos metodos en la API .NET "
            "moderna, Autodesk.Civil.DatabaseServices.AlignmentEntityCollection, que "
            "requiere pythonnet). "
            "LECCION: `AeccAlignments.Add(nombre, capa, estilo, estilo_etiquetas)` "
            "confirmado en la guia oficial de desarrollo de Civil3D (Civil3D-DevGuide, "
            "seccion 'Creating an Alignment'); estilo y estilo_etiquetas deben ser "
            "nombres de estilos YA EXISTENTES en el dibujo (Alignment Style / Label Set), "
            "la llamada falla si no existen."
        ),
    )
    async def crear_alineacion_vacia(
        nombre: str,
        estilo: str,
        estilo_etiquetas: str,
        capa: str = "0",
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre : str
            Nombre de la nueva alineacion.
        estilo : str
            Nombre de un Alignment Style ya existente en el dibujo.
        estilo_etiquetas : str
            Nombre de un Alignment Label Set ya existente en el dibujo.
        capa : str
            Capa donde se dibuja la alineacion.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                if _buscar_alineacion(client, nombre) is not None:
                    return {"error": f"Ya existe una alineacion llamada '{nombre}'."}
                try:
                    alig = client._doc.AlignmentsSiteless.Add(
                        nombre, capa, estilo, estilo_etiquetas
                    )
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo crear la alineacion (revisa que '{estilo}' y "
                            f"'{estilo_etiquetas}' existan como Alignment Style / Label "
                            f"Set en el dibujo): {exc}"
                        )
                    }
                return {"success": True, "nombre": alig.Name, "capa": capa}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="crear_alineacion_desde_polilinea",
        description=(
            "Crea una alineacion a partir de una polilinea 2D existente (identificada por "
            "handle). Es la via practica para crear alineaciones con geometria real via "
            "COM: en vez de anadir tangentes/curvas una a una (no confirmado en la API "
            "legacy, ver `crear_alineacion_vacia`), se construye la polilinea con la "
            "geometria deseada (tangentes rectas, arcos para las curvas) y se convierte "
            "de una vez. "
            "LECCION: `AeccAlignments.AddFromPolyline(nombre, capa, ObjectID_polilinea, "
            "estilo, estilo_etiquetas, anadir_curvas_entre_tangentes, "
            "borrar_polilinea_original)` confirmado en la guia oficial de desarrollo de "
            "Civil3D (Civil3D-DevGuide, seccion 'Creating an Alignment'). Si "
            "anadir_curvas_entre_tangentes=True, Civil3D inserta curvas libres en los "
            "vertices de la polilinea automaticamente (con el radio por defecto del "
            "dibujo); si la polilinea ya tiene arcos, esos se respetan como curvas fijas."
        ),
    )
    async def crear_alineacion_desde_polilinea(
        nombre: str,
        handle_polilinea: str,
        estilo: str,
        estilo_etiquetas: str,
        capa: str = "0",
        anadir_curvas_entre_tangentes: bool = False,
        borrar_polilinea_original: bool = False,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre : str
            Nombre de la nueva alineacion.
        handle_polilinea : str
            Handle hexadecimal de la polilinea 2D de origen.
        estilo : str
            Nombre de un Alignment Style ya existente en el dibujo.
        estilo_etiquetas : str
            Nombre de un Alignment Label Set ya existente en el dibujo.
        capa : str
            Capa donde se dibuja la alineacion.
        anadir_curvas_entre_tangentes : bool
            Si True, Civil3D inserta curvas libres en los vertices de la polilinea.
        borrar_polilinea_original : bool
            Si True, borra la polilinea de origen tras crear la alineacion.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                if _buscar_alineacion(client, nombre) is not None:
                    return {"error": f"Ya existe una alineacion llamada '{nombre}'."}
                try:
                    poly = client._doc.HandleToObject(handle_polilinea)
                except Exception as exc:
                    return {"error": f"No se encontro la polilinea '{handle_polilinea}': {exc}"}
                try:
                    alig = client._doc.AlignmentsSiteless.AddFromPolyline(
                        nombre,
                        capa,
                        poly.ObjectID,
                        estilo,
                        estilo_etiquetas,
                        anadir_curvas_entre_tangentes,
                        borrar_polilinea_original,
                    )
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo crear la alineacion desde la polilinea (revisa "
                            f"que '{estilo}'/'{estilo_etiquetas}' existan y que la "
                            f"polilinea sea 2D): {exc}"
                        )
                    }
                return {
                    "success": True,
                    "nombre": alig.Name,
                    "longitud": alig.Length,
                    "pk_inicio": alig.StartingStation,
                    "pk_fin": alig.EndingStation,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="borrar_alineacion",
        description=(
            "Borra una alineacion por nombre exacto. No borra los perfiles asociados a "
            "ella (comportamiento no verificado; revisar tras la prueba si quedan "
            "perfiles huerfanos)."
        ),
    )
    async def borrar_alineacion(nombre: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre)
                if alig is None:
                    return {"error": f"Alineacion '{nombre}' no encontrada."}
                alig.Delete()
                return {"success": True, "nombre": nombre}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="crear_perfil_superficie",
        description=(
            "Crea un perfil (rasante) para una alineacion muestreando las elevaciones de "
            "una superficie TIN existente. "
            "LECCION: `Alignment.Profiles.AddFromSurface(nombre, tipo_perfil, estilo, "
            "nombre_superficie, pk_inicio, pk_fin, capa)` confirmado en la guia oficial "
            "de desarrollo de Civil3D (Civil3D-DevGuide, 'Creating a Profile From a "
            "Surface'). "
            "LECCION: `tipo_perfil` es el enum COM `AeccProfileType`, RESUELTO el "
            "31/07/2026 leyendo la type library (aeccExistingGround=1, "
            "aeccFinishedGround=2, aeccSuperimposed=3). Aqui el valor correcto es 1 "
            "(terreno existente), que es el que trae por defecto: el perfil viene "
            "muestreado de una superficie. Para una rasante de proyecto usa "
            "`crear_perfil_diseno`, que por defecto pasa 2."
        ),
    )
    async def crear_perfil_superficie(
        nombre_alineacion: str,
        nombre_perfil: str,
        nombre_superficie: str,
        estilo: str,
        tipo_perfil: int = 1,
        capa: str = "0",
        pk_inicio: float | None = None,
        pk_fin: float | None = None,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion : str
            Nombre exacto de la alineacion.
        nombre_perfil : str
            Nombre del nuevo perfil.
        nombre_superficie : str
            Nombre de la superficie TIN de origen.
        tipo_perfil : int
            Enum COM AeccProfileType: 1=terreno existente (por defecto aqui),
            2=rasante de proyecto, 3=superpuesto.
        estilo : str
            Nombre de un Profile Style ya existente en el dibujo.
        capa : str
            Capa donde se dibuja el perfil.
        pk_inicio, pk_fin : float, opcional
            Rango de PK a muestrear; por defecto, todo el rango de la alineacion.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                pki = pk_inicio if pk_inicio is not None else alig.StartingStation
                pkf = pk_fin if pk_fin is not None else alig.EndingStation
                try:
                    perfil = alig.Profiles.AddFromSurface(
                        nombre_perfil, tipo_perfil, estilo, nombre_superficie, pki, pkf, capa
                    )
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo crear el perfil (revisa nombre_superficie, "
                            f"estilo y tipo_perfil): {exc}"
                        )
                    }
                return {
                    "success": True,
                    "alineacion": nombre_alineacion,
                    "perfil": perfil.Name,
                    "pk_inicio": pki,
                    "pk_fin": pkf,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}


    @mcp.tool(
        name="crear_perfil_diseno",
        description=(
            "Crea un perfil vacio (de diseno) para una alineacion, sin informacion de "
            "elevacion; la forma vertical se define despues anadiendo tramos con "
            "`anadir_tangente_perfil`. "
            "LECCION: `Alignment.Profiles.Add(nombre, tipo_perfil, estilo)` confirmado en "
            "la guia oficial de desarrollo de Civil3D (Civil3D-DevGuide, 'Creating a "
            "Profile Using Entities'). "
            "LECCION: `tipo_perfil` es el enum COM `AeccProfileType`, RESUELTO el "
            "31/07/2026 leyendo la type library (aeccExistingGround=1, "
            "aeccFinishedGround=2, aeccSuperimposed=3). Aqui el valor correcto es 2 "
            "(rasante de proyecto), que es el que trae por defecto. OJO: hasta el "
            "31/07/2026 esta tool exigia el valor al llamante y la campana de pruebas "
            "del 26/07 concluyo 'tipo_perfil=1 funciona' — funciona en el sentido de "
            "que no da error, pero etiqueta la rasante como TERRENO EXISTENTE. Si "
            "encuentras perfiles de diseno creados antes de esa fecha, revisa su tipo."
        ),
    )
    async def crear_perfil_diseno(
        nombre_alineacion: str,
        nombre_perfil: str,
        estilo: str,
        tipo_perfil: int = 2,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                try:
                    perfil = alig.Profiles.Add(nombre_perfil, tipo_perfil, estilo)
                except Exception as exc:
                    return {
                        "error": f"No se pudo crear el perfil (revisa estilo y tipo_perfil): {exc}"
                    }
                return {"success": True, "alineacion": nombre_alineacion, "perfil": perfil.Name}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="anadir_tangente_perfil",
        description=(
            "Anade un tramo recto (tangente fija) a un perfil de diseno vacio (creado "
            "con `crear_perfil_diseno`), definido por dos puntos estacion-elevacion "
            "(PK, cota) — NO son coordenadas X,Y. Los extremos de tangentes sucesivas son "
            "los PVI del perfil (no existe un metodo separado 'anadir_pvi' confirmado; "
            "los PVI emergen de los extremos de las tangentes, igual que en la interfaz "
            "de Civil3D). "
            "LECCION: `Profile.Entities.AddFixedTangent([pk1, elev1], [pk2, elev2])` "
            "confirmado en la guia oficial de desarrollo de Civil3D (Civil3D-DevGuide, "
            "'Creating a Profile Using Entities'). "
            "LECCION: para acordonar dos tangentes con una curva vertical (parabola) usa "
            "`anadir_curva_vertical_perfil`, que necesita el `id_entidad` que devuelve "
            "ESTA tool — apuntalo al crear cada tangente."
        ),
    )
    async def anadir_tangente_perfil(
        nombre_alineacion: str,
        nombre_perfil: str,
        pk_inicio: float,
        elevacion_inicio: float,
        pk_fin: float,
        elevacion_fin: float,
    ) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                perfil = None
                for p in iter_com_collection(alig.Profiles):
                    if p.Name == nombre_perfil:
                        perfil = p
                        break
                if perfil is None:
                    return {
                        "error": f"Perfil '{nombre_perfil}' no encontrado en '{nombre_alineacion}'."
                    }
                loc1 = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [pk_inicio, elevacion_inicio]
                )
                loc2 = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [pk_fin, elevacion_fin]
                )
                try:
                    tangente = perfil.Entities.AddFixedTangent(loc1, loc2)
                except Exception as exc:
                    return {"error": f"No se pudo anadir la tangente: {exc}"}
                return {
                    "success": True,
                    "alineacion": nombre_alineacion,
                    "perfil": nombre_perfil,
                    "id_entidad": tangente.Id,
                    "pk_inicio": pk_inicio,
                    "elevacion_inicio": elevacion_inicio,
                    "pk_fin": pk_fin,
                    "elevacion_fin": elevacion_fin,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="anadir_curva_vertical_perfil",
        description=(
            "Acuerda dos tangentes consecutivas de un perfil de diseno con una curva "
            "vertical (parabola simetrica), por longitud o por valor K. Las dos "
            "tangentes deben existir ya: se identifican por el `id_entidad` que "
            "devuelve `anadir_tangente_perfil`. "
            "LECCION: firmas leidas de la type library el 31/07/2026 (metodo de la "
            "seccion 21 del wiki, no documentacion oficial): "
            "`Profile.Entities.AddFreeSymmetricParabolaByLength(nBeforeId, nAfterId, "
            "eVerticalCurveType, dLength, bPreferFlat)` y `...ByK(nBeforeId, nAfterId, "
            "eVerticalCurveType, dK)`. "
            "LECCION: `tipo_curva` es el enum COM `AeccProfileVerticalCurveType`: "
            "1=aeccSag (concava, valle), 2=aeccCrest (convexa, cima). Debe COINCIDIR "
            "con la geometria real de las dos tangentes; si te equivocas de tipo, "
            "Civil3D rechaza la curva o la resuelve de forma inesperada. "
            "LECCION: `preferir_plano` es el parametro `bPreferFlat` del metodo por "
            "longitud (no existe en la variante por K); resuelve la ambiguedad cuando "
            "hay mas de una solucion valida. Por defecto False. "
            "LECCION: tool de ESCRITURA nacida de firmas leidas en la typelib, no de "
            "comportamiento probado — la typelib garantiza que el metodo existe y que "
            "parametros pide, NO que haga lo esperado. Verificar el resultado real con "
            "`info_perfil` tras cada llamada."
        ),
    )
    async def anadir_curva_vertical_perfil(
        nombre_alineacion: str,
        nombre_perfil: str,
        id_tangente_antes: int,
        id_tangente_despues: int,
        tipo_curva: int,
        longitud: float | None = None,
        valor_k: float | None = None,
        preferir_plano: bool = False,
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        nombre_alineacion, nombre_perfil : str
            Alineacion y perfil de diseno donde estan las tangentes.
        id_tangente_antes, id_tangente_despues : int
            `id_entidad` de las dos tangentes a acordar, en orden de PK creciente
            (devueltos por `anadir_tangente_perfil`).
        tipo_curva : int
            Enum AeccProfileVerticalCurveType: 1=concava (sag), 2=convexa (crest).
        longitud : float, opcional
            Longitud de la curva en metros. Excluyente con `valor_k`.
        valor_k : float, opcional
            Valor K de la curva. Excluyente con `longitud`.
        preferir_plano : bool
            Parametro `bPreferFlat`, solo aplica al metodo por longitud.
        """
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                if (longitud is None) == (valor_k is None):
                    return {
                        "error": "Indica exactamente uno de los dos: longitud o valor_k."
                    }
                if tipo_curva not in (1, 2):
                    return {
                        "error": "tipo_curva debe ser 1 (concava/sag) o 2 (convexa/crest)."
                    }
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                perfil = None
                for p in iter_com_collection(alig.Profiles):
                    if p.Name == nombre_perfil:
                        perfil = p
                        break
                if perfil is None:
                    return {
                        "error": f"Perfil '{nombre_perfil}' no encontrado en '{nombre_alineacion}'."
                    }
                try:
                    if longitud is not None:
                        curva = perfil.Entities.AddFreeSymmetricParabolaByLength(
                            id_tangente_antes,
                            id_tangente_despues,
                            tipo_curva,
                            longitud,
                            preferir_plano,
                        )
                        metodo = "longitud"
                    else:
                        curva = perfil.Entities.AddFreeSymmetricParabolaByK(
                            id_tangente_antes,
                            id_tangente_despues,
                            tipo_curva,
                            valor_k,
                        )
                        metodo = "valor_k"
                except Exception as exc:
                    return {
                        "error": (
                            f"No se pudo anadir la curva vertical (revisa que los dos "
                            f"id_entidad existan, esten en orden de PK creciente y que "
                            f"tipo_curva coincida con la geometria real): {exc}"
                        )
                    }
                resultado = {
                    "success": True,
                    "alineacion": nombre_alineacion,
                    "perfil": nombre_perfil,
                    "metodo": metodo,
                    "tipo_curva": "concava (sag)" if tipo_curva == 1 else "convexa (crest)",
                    "id_tangente_antes": id_tangente_antes,
                    "id_tangente_despues": id_tangente_despues,
                }
                # Capturar los datos ANTES de cualquier operacion posterior: el objeto
                # COM puede invalidarse. Cada propiedad falla sola, sin abortar el resto.
                for prop in ("Id", "Length", "K", "Radius"):
                    try:
                        resultado[prop.lower()] = getattr(curva, prop)
                    except Exception:
                        pass
                return resultado
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="eliminar_perfil",
        description="Borra un perfil de una alineacion por nombre exacto.",
    )
    async def eliminar_perfil(nombre_alineacion: str, nombre_perfil: str) -> dict[str, Any]:
        try:
            def _run():
                if client._doc is None:
                    raise Civil3DError("Civil 3D no conectado.")
                alig = _buscar_alineacion(client, nombre_alineacion)
                if alig is None:
                    return {"error": f"Alineacion '{nombre_alineacion}' no encontrada."}
                perfil = None
                for p in iter_com_collection(alig.Profiles):
                    if p.Name == nombre_perfil:
                        perfil = p
                        break
                if perfil is None:
                    return {
                        "error": f"Perfil '{nombre_perfil}' no encontrado en '{nombre_alineacion}'."
                    }
                perfil.Delete()
                return {"success": True, "alineacion": nombre_alineacion, "perfil": nombre_perfil}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
