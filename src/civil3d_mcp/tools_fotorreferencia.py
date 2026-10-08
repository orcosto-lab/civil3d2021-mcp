"""
tools_fotorreferencia.py  -  Insercion de ortofoto georreferenciada en el dibujo activo

Toma la extension real de los objetos del dibujo (EXTMIN/EXTMAX + margen), descarga
la ortofoto correspondiente del servicio WMS publico del IGN (PNOA, EPSG:25830),
aplica un realce de nitidez (unsharp mask, Pillow) y la inserta en la capa
"99 Ortofotos" via AddRaster - metodo COM nativo del objeto ModelSpace, sin
SendCommand (mismo patron que zoom_extension/zoom en tools_view.py).

Verificado por prueba directa antes de implementar (22/07/2026, sesion Prosperidad):
- AddRaster(ruta, punto_insercion, escala, rotacion) crea un AcadRasterImage real.
- El PNG que devuelve el WMS del IGN no trae metadatos DPI -> AddRaster calcula un
  tamano base sin resolucion conocida, y "escala" es directamente el ANCHO final en
  unidades de dibujo (metros, dibujo en EPSG:25830). El ALTO se deriva solo de escala
  respetando el aspect ratio real en pixeles de la imagen (confirmado con una imagen
  NO cuadrada 800x400px / 200x100m: escala=200 -> ImageWidth=200.0, ImageHeight=100.0,
  sin distorsion). Punto de insercion = esquina inferior izquierda (confirmado via
  GetBoundingBox).
- Probado insertando y borrando, sin dejar rastro, antes de tocar ningun
  dibujo real.

Diseno extensible a otras fuentes: _descargar_imagen(bbox, fuente) es el unico punto
que conoce la fuente concreta (hoy solo "pnoa"); anadir un proveedor nuevo es anadir
una rama ahi (y su propia funcion _descargar_imagen_<fuente>), sin tocar el resto.

Estado tools_fotorreferencia.py / fotorreferencia: ✅ OK, confirmado
24/07/2026.

--- foto_mejorada (anadida 24/07/2026) ---

Segunda herramienta del mismo modulo: inserta una version de la ortofoto mejorada
FUERA del servidor (hoy: subida por el usuario a un editor de imagen tipo ChatGPT; manana
podria ser cualquier otro), en la misma posicion real que la ortofoto original ya
insertada por `fotorreferencia`, en una capa separada ("98 Mejorada" por defecto)
para poder comparar ambas superpuestas sin perder ninguna.

Diseno (decisiones de diseno, sesion 24/07/2026):
- La imagen original SIEMPRE se conserva en su capa; nunca se borra ni se sustituye.
  Si no esta presente cuando se llama a `foto_mejorada`, se regenera automaticamente
  llamando a la logica de `fotorreferencia` desde cero (misma capa "99 Ortofotos").
- Georreferencia de la imagen mejorada = la del raster original YA INSERTADO en el
  dibujo (capa_referencia), leida directamente de la entidad (GetBoundingBox +
  ImageWidth) - NO se reconstruye desde EXTMIN/EXTMAX. Mas robusto: no depende de
  que la geometria del dibujo no haya cambiado (ver seccion 17.1 del wiki para el
  procedimiento manual usado antes de tener esta tool, cuando el raster original
  ya no estaba en el dibujo).
- Verificacion antes de insertar (para no meter una imagen equivocada o distorsionada):
  se compara el aspect ratio en pixeles de la imagen mejorada contra el de la imagen
  original (leido de las propiedades .Width/.Height del raster original, sin necesidad
  de localizar ni reabrir el PNG original en disco - la entidad COM ya lo sabe).
  Tolerancia por defecto 2% (decidida por diseno); si se supera, NO se inserta y se
  devuelve el detalle para que el usuario decida.
- Si hay mas de una imagen en capa_referencia (dibujos grandes con varias teselas),
  la herramienta NO intenta adivinar cual es la correspondiente: devuelve la lista de
  candidatos (handle, tamano) y pide que se repita la llamada con handle_referencia.

Estado foto_mejorada: ⏳ recien creada, pendiente de probar en un dibujo real y de
confirmacion del usuario (no marcar como OK en TOOLS.md hasta entonces). Pendiente en
particular: verificar en la practica el mensaje de error cuando hay >1 candidato, y
el flujo de regeneracion automatica cuando no hay ninguna imagen todavia.

--- mejorar_ortofoto_local (anadida 28/07/2026) ---

Tercera herramienta del modulo: genera la version "mejorada" que antes producia el usuario
subiendo el PNG a ChatGPT a mano. Sustituye ese paso por un pipeline 100% local:
RealESRGAN (ejecutable portable `realesrgan-ncnn-vulkan.exe`, sin Python/CUDA, en
`Filtros/realesrgan/` dentro del propio proyecto) + reduccion Pillow (LANCZOS).

Decision de arquitectura (sesion 28/07/2026): tool separada de `foto_mejorada`, no
fusionada. `mejorar_ortofoto_local` solo genera el PNG en disco y no toca el dibujo;
`foto_mejorada` sigue siendo la unica que inserta, exactamente igual que antes (su
`ruta_imagen_mejorada` ahora puede venir de esta tool en vez de una subida manual).
Cero riesgo sobre `foto_mejorada`, que ya esta confirmada en produccion.

Por que este pipeline y no otras alternativas evaluadas antes (ver tambien wiki):
- API de ChatGPT/OpenAI (gpt-image-1): descartada por coste real por imagen
  y por requerir verificacion de organizacion con ID - no compensa para uso ocasional.
- RealESRGAN "a secas" (solo upscale x4, sin reducir): peso disparado (~3 MB para una
  tesela de 434x265px que en original pesa ~260 KB) - descartado
  explicitamente por el peso del archivo.
- RealESRGAN + reduccion Lanczos (el elegido): el escalado x4 sintetiza detalle de
  alta frecuencia (superresolucion real, no solo nitidez); la reduccion posterior lo
  funde con la imagen en vez de perderlo - mas nitido que un sharpen directo al tamano
  original, sin el peso del x4 completo. 100% local, sin coste, sin cuenta ni
  verificacion de terceros.

Nota importante de honestidad tecnica (aplicable igual que el modelo de ChatGPT): el
escalado sigue siendo generativo (el modelo sintetiza plausible, no mide realidad) -
igual que la version manual de ChatGPT que el usuario ya daba por buena. Aceptable aqui
porque el resultado es SIEMPRE una capa de comparacion visual ("98 Mejorada"), nunca
sustituye a la ortofoto original que sigue intacta en "99 Ortofotos".

Modelos de RealESRGAN: el propio release oficial de `Real-ESRGAN-ncnn-vulkan` NO trae
la carpeta `models/` en NINGUNA de sus versiones (bug conocido, ver issue #29 del
repo, sin resolver). Los modelos de este proyecto se sacaron de un release del OTRO
repo (`xinntao/Real-ESRGAN`, tag v0.2.5.0, asset "-ubuntu.zip" pese a ser Windows: la
carpeta `models/` son solo datos `.bin`/`.param`, no binarios de plataforma). Modelo
usado: `realesrgan-x4plus` (fotografia real general; NO `x4plus-anime` ni
`animevideov3`, pensados para dibujos/video).

Prueba de pipeline hecha ANTES de escribir la tool (26/07/2026,
`_ortofoto_01.png` 434x265px/261 KB, via Desktop Commander sobre la maquina real -
GPU detectada: NVIDIA GeForce RTX 3050 Laptop): upscale x4 -> 1736x1060/2.97 MB;
reduccion Lanczos a 2x el original -> 868x530/831 KB. **Aprobada
("perfecta")** tras comparar tambien contra el x4 sin reducir (`_ortofoto_04.png`).
escala_final por defecto = 2.0 (el resultado final mide 2x el original en cada eje).

Estado mejorar_ortofoto_local: ⏳ pipeline ya validado manualmente, pero la TOOL en si
(wrapper MCP) recien escrita - pendiente de reinicio de Claude Desktop y de que el usuario
la pruebe llamandola de verdad antes de marcarla OK en TOOLS.md.
"""
from __future__ import annotations
import asyncio
import io
import logging
import math
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pythoncom
from win32com.client import VARIANT
from mcp.server.fastmcp import FastMCP

from .client import Civil3DClient

log = logging.getLogger("civil3d_mcp.tools.fotorreferencia")

# --- Config fuente PNOA (IGN, servicio publico, sin autenticacion) ---
PNOA_WMS_URL = "https://www.ign.es/wms-inspire/pnoa-ma"
PNOA_LAYER = "OI.OrthoimageCoverage"
PNOA_RESOLUCION_M = 0.25  # m/pixel nativo de la ortofoto PNOA maxima actualidad
PNOA_MAX_PX = 4096  # MaxWidth/MaxHeight declarados por el servicio (GetCapabilities)

CAPA_ORTOFOTOS = "99 Ortofotos"
CAPA_MEJORADA = "98 Mejorada"

# Parametros del realce de nitidez (Pillow UnsharpMask, estilo "Photoshop"):
# no anade resolucion real, solo refuerza contraste en bordes ya presentes.
REALCE_RADIUS = 2
REALCE_PERCENT = 150
REALCE_THRESHOLD = 2

# Tolerancia por defecto para el chequeo de aspect ratio en foto_mejorada.
TOLERANCIA_ASPECTO_DEFECTO = 0.02

# --- Config mejorar_ortofoto_local (RealESRGAN portable + reduccion Lanczos) ---
# Ruta relativa al propio modulo (portable entre maquinas, ver 00_NOTAS_PROYECTO.md
# seccion de config por PC - no depende de que la letra de unidad sea igual en todas).
FILTROS_DIR = Path(__file__).resolve().parent.parent.parent / "Filtros"
REALESRGAN_EXE = FILTROS_DIR / "realesrgan" / "realesrgan-ncnn-vulkan.exe"
REALESRGAN_MODELS = FILTROS_DIR / "realesrgan" / "models"

MODELO_REALESRGAN_DEFECTO = "realesrgan-x4plus"  # fotografia real; NO usar los de anime/video
ESCALA_UPSCALE_NATIVA = 4  # factor fijo del modelo x4plus, no configurable
ESCALA_FINAL_DEFECTO = 2.0  # resultado final = 2x el tamano ORIGINAL (aprobado)
TIMEOUT_REALESRGAN_S = 300


def _punto(x: float, y: float, z: float = 0.0) -> VARIANT:
    """Punto 3D como VARIANT para AddRaster (mismo helper que tools_view.py)."""
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z])


def _descargar_imagen_pnoa(minx: float, miny: float, maxx: float, maxy: float) -> bytes:
    """
    Pide al WMS del IGN la ortofoto PNOA para un bbox en EPSG:25830 (metros).
    Resolucion fija a la nativa PNOA MA (0.25 m/pixel), sin sobremuestreo.
    """
    ancho_m = maxx - minx
    alto_m = maxy - miny
    width_px = max(1, min(PNOA_MAX_PX, round(ancho_m / PNOA_RESOLUCION_M)))
    height_px = max(1, min(PNOA_MAX_PX, round(alto_m / PNOA_RESOLUCION_M)))
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": PNOA_LAYER,
        "STYLES": "",
        "CRS": "EPSG:25830",
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(width_px),
        "HEIGHT": str(height_px),
        "FORMAT": "image/png",
    }
    url = PNOA_WMS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "civil3d-mcp/fotorreferencia"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _descargar_imagen(bbox: tuple[float, float, float, float], fuente: str) -> bytes:
    """Punto unico de despacho por fuente. Anadir fuentes nuevas aqui."""
    fuente_norm = fuente.strip().lower()
    if fuente_norm == "pnoa":
        return _descargar_imagen_pnoa(*bbox)
    raise ValueError(f"Fuente de imagen no soportada: '{fuente}' (disponible: 'pnoa')")


def _realzar_nitidez(imagen_bytes: bytes):
    """Unsharp mask (Pillow). No anade resolucion real, solo refuerza bordes."""
    from PIL import Image, ImageFilter

    img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    return img.filter(
        ImageFilter.UnsharpMask(
            radius=REALCE_RADIUS, percent=REALCE_PERCENT, threshold=REALCE_THRESHOLD
        )
    )


def _dividir_en_teselas(
    minx: float, miny: float, maxx: float, maxy: float, max_lado_m: float
) -> list[tuple[float, float, float, float]]:
    """Trocea un bbox en una cuadricula de teselas, cada una <= max_lado_m de lado."""
    ancho = maxx - minx
    alto = maxy - miny
    ncols = max(1, math.ceil(ancho / max_lado_m))
    nfilas = max(1, math.ceil(alto / max_lado_m))
    lado_x = ancho / ncols
    lado_y = alto / nfilas
    teselas = []
    for j in range(nfilas):
        for i in range(ncols):
            tminx = minx + i * lado_x
            tmaxx = minx + (i + 1) * lado_x
            tminy = miny + j * lado_y
            tmaxy = miny + (j + 1) * lado_y
            teselas.append((tminx, tminy, tmaxx, tmaxy))
    return teselas


def _generar_fotorreferencia(doc, margen_m: float, fuente: str) -> dict[str, Any]:
    """
    Cuerpo real de la tool `fotorreferencia` (extraido para poder reutilizarlo desde
    `foto_mejorada` cuando no hay ninguna imagen todavia en capa_referencia).
    """
    try:
        doc.Application.ZoomExtents()
    except Exception:
        pass  # no critico, solo intenta refrescar EXTMIN/EXTMAX

    extmin = list(doc.GetVariable("EXTMIN"))
    extmax = list(doc.GetVariable("EXTMAX"))
    minx, miny = extmin[0] - margen_m, extmin[1] - margen_m
    maxx, maxy = extmax[0] + margen_m, extmax[1] + margen_m

    if maxx <= minx or maxy <= miny:
        return {
            "error": (
                "Extension del dibujo invalida o dibujo vacio "
                f"(EXTMIN={extmin}, EXTMAX={extmax})"
            )
        }

    max_lado_m = PNOA_MAX_PX * PNOA_RESOLUCION_M  # 1024 m
    teselas = _dividir_en_teselas(minx, miny, maxx, maxy, max_lado_m)

    capa_existe = any(c.Name.lower() == CAPA_ORTOFOTOS.lower() for c in doc.Layers)
    if not capa_existe:
        doc.Layers.Add(CAPA_ORTOFOTOS)

    carpeta = os.path.dirname(doc.FullName) or "."
    base_nombre = os.path.splitext(os.path.basename(doc.FullName))[0]

    insertadas = []
    for idx, (tminx, tminy, tmaxx, tmaxy) in enumerate(teselas):
        try:
            imagen_bytes = _descargar_imagen((tminx, tminy, tmaxx, tmaxy), fuente)
            img = _realzar_nitidez(imagen_bytes)

            nombre_archivo = f"{base_nombre}_ortofoto_{idx + 1:02d}.png"
            ruta = os.path.join(carpeta, nombre_archivo)
            img.save(ruta)

            ancho_m = tmaxx - tminx
            raster = doc.ModelSpace.AddRaster(
                ruta, _punto(tminx, tminy, 0.0), ancho_m, 0.0
            )
            raster.Layer = CAPA_ORTOFOTOS

            insertadas.append({
                "tesela": idx + 1,
                "archivo": ruta,
                "handle": raster.Handle,
                "bbox": [tminx, tminy, tmaxx, tmaxy],
            })
        except Exception as e:
            insertadas.append({"tesela": idx + 1, "error": str(e)})

    try:
        doc.Regen(1)  # acAllViewports; intento de forzar refresco de paletas (ver wiki seccion 18)
    except Exception:
        pass  # no critico

    return {
        "success": True,
        "fuente": fuente,
        "capa": CAPA_ORTOFOTOS,
        "margen_m": margen_m,
        "extension_pedida": [minx, miny, maxx, maxy],
        "total_teselas": len(teselas),
        "insertadas": insertadas,
    }


def _buscar_rasters_en_capa(doc, capa: str) -> list:
    """Devuelve todos los AcDbRasterImage de ModelSpace cuya capa coincide (case-insensitive)."""
    capa_norm = capa.strip().lower()
    encontrados = []
    for obj in doc.ModelSpace:
        try:
            if obj.ObjectName == "AcDbRasterImage" and obj.Layer.lower() == capa_norm:
                encontrados.append(obj)
        except Exception:
            pass
    return encontrados


def _mejorar_ortofoto_local_sync(
    ruta_imagen_original: str,
    ruta_salida: str,
    escala_final: float,
    modelo: str,
) -> dict[str, Any]:
    """
    Cuerpo real de `mejorar_ortofoto_local`. Sincrono a proposito (subprocess +
    PIL bloqueantes); la tool async lo lanza via asyncio.to_thread. No toca Civil 3D
    para nada - no usa run_com ni client.
    """
    from PIL import Image

    if not os.path.isfile(ruta_imagen_original):
        return {"error": f"No existe el archivo: {ruta_imagen_original}"}

    if not REALESRGAN_EXE.is_file():
        return {
            "error": (
                f"No se encuentra el ejecutable de RealESRGAN en '{REALESRGAN_EXE}'. "
                "Ver cabecera del modulo para de donde descargarlo."
            )
        }
    if not REALESRGAN_MODELS.is_dir():
        return {
            "error": (
                f"No se encuentra la carpeta de modelos en '{REALESRGAN_MODELS}'. Los "
                "modelos NO vienen en el release oficial (bug conocido, ver cabecera "
                "del modulo) - hay que sacarlos del release v0.2.5.0 del repo "
                "xinntao/Real-ESRGAN."
            )
        }

    if not (0 < escala_final <= ESCALA_UPSCALE_NATIVA):
        return {
            "error": (
                f"escala_final={escala_final} fuera de rango: debe ser > 0 y <= "
                f"{ESCALA_UPSCALE_NATIVA} (factor nativo del modelo x4plus; no se puede "
                "pedir mas resolucion final que la que produce el propio upscale)."
            )
        }

    carpeta = os.path.dirname(os.path.abspath(ruta_imagen_original))
    base_nombre = os.path.splitext(os.path.basename(ruta_imagen_original))[0]

    if not ruta_salida:
        ruta_salida = os.path.join(carpeta, f"{base_nombre}_mejorada_local.png")

    ruta_tmp_upscale = os.path.join(carpeta, f"{base_nombre}_tmp_realesrgan_x4.png")

    with Image.open(ruta_imagen_original) as img_orig:
        ancho_orig, alto_orig = img_orig.size

    comando = [
        str(REALESRGAN_EXE),
        "-i", os.path.abspath(ruta_imagen_original),
        "-o", ruta_tmp_upscale,
        "-m", str(REALESRGAN_MODELS),
        "-n", modelo,
        "-s", str(ESCALA_UPSCALE_NATIVA),
    ]

    try:
        resultado = subprocess.run(
            comando, capture_output=True, text=True, timeout=TIMEOUT_REALESRGAN_S
        )
    except subprocess.TimeoutExpired:
        return {
            "error": (
                f"RealESRGAN no termino en {TIMEOUT_REALESRGAN_S}s (imagen demasiado "
                "grande o GPU ocupada)."
            )
        }
    except OSError as e:
        return {"error": f"No se pudo ejecutar el .exe de RealESRGAN: {e}"}

    if resultado.returncode != 0 or not os.path.isfile(ruta_tmp_upscale):
        return {
            "error": (
                f"RealESRGAN termino con codigo {resultado.returncode} y no genero "
                f"salida valida. stderr: {resultado.stderr.strip()[:500]}"
            )
        }

    try:
        with Image.open(ruta_tmp_upscale) as img_upscale:
            ancho_final = max(1, round(ancho_orig * escala_final))
            alto_final = max(1, round(alto_orig * escala_final))
            img_final = img_upscale.resize((ancho_final, alto_final), Image.LANCZOS)
            img_final.save(ruta_salida, optimize=True)
    finally:
        try:
            os.remove(ruta_tmp_upscale)
        except OSError:
            pass

    return {
        "success": True,
        "ruta_salida": ruta_salida,
        "modelo": modelo,
        "dims_original_px": [ancho_orig, alto_orig],
        "dims_finales_px": [ancho_final, alto_final],
        "escala_final": escala_final,
        "peso_bytes": os.path.getsize(ruta_salida),
    }


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="fotorreferencia",
        description=(
            "Inserta ortofoto georreferenciada (PNOA por defecto) en el dibujo activo, "
            "cubriendo la extension real de sus objetos (EXTMIN/EXTMAX + margen_m). Si "
            "la extension supera el limite de una tesela WMS (1024x1024 m a 25 cm/px), "
            "la trocea en varias imagenes contiguas, cada una insertada por separado. "
            "Aplica SIEMPRE un realce de nitidez (unsharp mask, Pillow): esto NO anade "
            "resolucion real, solo refuerza el contraste de bordes ya presentes en los "
            "pixeles originales - no usar el resultado como fuente de medicion o trazado "
            "de detalle fino. Crea la capa '99 Ortofotos' si no existe e inserta ahi cada "
            "tesela via AddRaster (metodo COM nativo del ModelSpace, sin SendCommand - "
            "verificado: la escala pasada a AddRaster es el ancho final en metros, el "
            "alto se deriva solo del aspect ratio real en pixeles, sin distorsion; punto "
            "de insercion = esquina inferior izquierda). Los PNG generados se guardan "
            "junto al DWG activo, nombrados '<nombre_dwg>_ortofoto_NN.png'. Diseno "
            "extensible: parametro fuente admite anadir proveedores nuevos en el futuro "
            "(hoy solo 'pnoa'). Ver tambien 'foto_mejorada' para insertar versiones "
            "mejoradas externamente de estas mismas imagenes."
        ),
    )
    async def fotorreferencia(margen_m: float = 20.0, fuente: str = "pnoa") -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                return _generar_fotorreferencia(doc, margen_m, fuente)

            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="foto_mejorada",
        description=(
            "Inserta en el dibujo activo una version MEJORADA EXTERNAMENTE (p.ej. subida "
            "por el usuario a ChatGPT u otra IA para aumentar resolucion/nitidez) de una "
            "ortofoto ya generada por 'fotorreferencia', en la MISMA posicion real que la "
            "original, en una capa separada (capa_destino, '98 Mejorada' por defecto) para "
            "poder comparar ambas superpuestas. La imagen original NUNCA se borra ni se "
            "sustituye. Georreferencia = la del raster original ya insertado en "
            "capa_referencia ('99 Ortofotos' por defecto), leida directamente de la entidad "
            "(GetBoundingBox + ImageWidth) - no se recalcula desde EXTMIN/EXTMAX, asi no "
            "depende de que el dibujo no haya cambiado desde que se genero. Si no hay "
            "ninguna imagen en capa_referencia, la regenera automaticamente llamando a la "
            "logica de 'fotorreferencia' (con margen_m/fuente indicados) antes de insertar "
            "la mejorada. Si hay MAS DE UNA imagen en capa_referencia (dibujos con varias "
            "teselas), no adivina cual es la correspondiente: devuelve la lista de "
            "candidatos (handle, tamano) y pide repetir la llamada indicando "
            "handle_referencia. Antes de insertar compara el aspect ratio en pixeles de la "
            "imagen mejorada contra el de la original (tolerancia_aspecto, 2% por defecto) "
            "para evitar insertar una imagen de otra zona o con relacion de aspecto "
            "alterada (recorte/relleno del editor externo); si se supera la tolerancia, NO "
            "inserta y devuelve el detalle."
        ),
    )
    async def foto_mejorada(
        ruta_imagen_mejorada: str,
        capa_destino: str = CAPA_MEJORADA,
        capa_referencia: str = CAPA_ORTOFOTOS,
        handle_referencia: str = "",
        tolerancia_aspecto: float = TOLERANCIA_ASPECTO_DEFECTO,
        margen_m: float = 20.0,
        fuente: str = "pnoa",
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc

                if not os.path.isfile(ruta_imagen_mejorada):
                    return {"error": f"No existe el archivo: {ruta_imagen_mejorada}"}

                raster_ref = None

                if handle_referencia:
                    try:
                        obj = doc.HandleToObject(handle_referencia)
                    except Exception as e:
                        return {
                            "error": f"No se pudo resolver handle_referencia '{handle_referencia}': {e}"
                        }
                    if obj.ObjectName != "AcDbRasterImage":
                        return {
                            "error": (
                                f"El handle '{handle_referencia}' no es una imagen raster "
                                f"(es {obj.ObjectName})"
                            )
                        }
                    raster_ref = obj
                else:
                    candidatos = _buscar_rasters_en_capa(doc, capa_referencia)

                    if len(candidatos) == 0:
                        if capa_referencia.strip().lower() == CAPA_ORTOFOTOS.lower():
                            resultado_regen = _generar_fotorreferencia(doc, margen_m, fuente)
                            if "error" in resultado_regen:
                                return {
                                    "error": (
                                        f"No habia ninguna imagen en la capa '{capa_referencia}' "
                                        "y la regeneracion automatica via fotorreferencia fallo: "
                                        f"{resultado_regen['error']}"
                                    )
                                }
                            candidatos = _buscar_rasters_en_capa(doc, capa_referencia)

                        if len(candidatos) == 0:
                            return {
                                "error": (
                                    f"No hay ninguna imagen en la capa '{capa_referencia}' y no "
                                    "se pudo generar automaticamente. Ejecuta 'fotorreferencia' "
                                    "manualmente primero."
                                )
                            }

                    if len(candidatos) > 1:
                        return {
                            "error": (
                                f"Hay {len(candidatos)} imagenes en la capa '{capa_referencia}'; "
                                "especifica cual es la referencia con el parametro "
                                "handle_referencia."
                            ),
                            "candidatos": [
                                {
                                    "handle": c.Handle,
                                    "ancho_px": c.Width,
                                    "alto_px": c.Height,
                                    "ancho_m": c.ImageWidth,
                                }
                                for c in candidatos
                            ],
                        }

                    raster_ref = candidatos[0]

                from PIL import Image

                with Image.open(ruta_imagen_mejorada) as img_nueva:
                    w_nueva, h_nueva = img_nueva.size

                w_ref, h_ref = raster_ref.Width, raster_ref.Height
                aspecto_ref = w_ref / h_ref
                aspecto_nueva = w_nueva / h_nueva
                diferencia_relativa = abs(aspecto_nueva - aspecto_ref) / aspecto_ref

                if diferencia_relativa > tolerancia_aspecto:
                    return {
                        "error": (
                            "La imagen mejorada no parece corresponder a la misma zona (o "
                            "cambio de relacion de aspecto): "
                            f"original={aspecto_ref:.4f} ({w_ref:.0f}x{h_ref:.0f} px) vs "
                            f"mejorada={aspecto_nueva:.4f} ({w_nueva}x{h_nueva} px), "
                            f"diferencia {diferencia_relativa * 100:.2f}% > tolerancia "
                            f"{tolerancia_aspecto * 100:.1f}%. No se ha insertado nada."
                        ),
                        "referencia_handle": raster_ref.Handle,
                    }

                bbox_min, bbox_max = raster_ref.GetBoundingBox()
                punto = _punto(bbox_min[0], bbox_min[1], 0.0)
                ancho_m = raster_ref.ImageWidth

                capa_existe = any(c.Name.lower() == capa_destino.lower() for c in doc.Layers)
                if not capa_existe:
                    doc.Layers.Add(capa_destino)

                raster_nuevo = doc.ModelSpace.AddRaster(
                    ruta_imagen_mejorada, punto, ancho_m, 0.0
                )
                raster_nuevo.Layer = capa_destino

                try:
                    doc.Regen(1)  # acAllViewports; intento de forzar refresco de paletas (ver wiki seccion 18)
                except Exception:
                    pass  # no critico

                return {
                    "success": True,
                    "handle": raster_nuevo.Handle,
                    "capa": capa_destino,
                    "referencia_handle": raster_ref.Handle,
                    "referencia_capa": raster_ref.Layer,
                    "ancho_m": ancho_m,
                    "aspecto_original": aspecto_ref,
                    "aspecto_mejorada": aspecto_nueva,
                    "diferencia_relativa_pct": diferencia_relativa * 100,
                }

            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="mejorar_ortofoto_local",
        description=(
            "Genera una version MEJORADA 100% LOCAL (sin subir nada a ningun servicio "
            "externo, sin coste, sin cuenta de terceros) de una imagen ya generada por "
            "'fotorreferencia'. Pipeline: RealESRGAN (ejecutable portable "
            "'realesrgan-ncnn-vulkan.exe', sin Python/CUDA, en Filtros/realesrgan/ dentro "
            "del proyecto; modelo 'realesrgan-x4plus' por defecto) hace un upscale x4 "
            "fijo, y despues Pillow (LANCZOS) reduce el resultado a 'escala_final' veces "
            "el tamano ORIGINAL (por defecto 2x). Esa reduccion es la que aporta la "
            "mejora de nitidez visible sin disparar el peso del archivo (aprox. 800 KB "
            "para una tesela tipica de 434x265px, frente a varios MB si se dejara el x4 "
            "completo sin reducir). Guarda el PNG junto al original (o en ruta_salida si "
            "se indica) y NO toca el dibujo de Civil 3D - la ruta devuelta se pasa tal "
            "cual a 'foto_mejorada' para insertarla, exactamente igual que si viniera de "
            "una mejora manual externa. Pipeline aprobado tras prueba "
            "comparativa (ver detalle en el modulo y en la wiki); escala_final no puede "
            "superar 4 (el modelo x4plus no produce mas resolucion real que esa)."
        ),
    )
    async def mejorar_ortofoto_local(
        ruta_imagen_original: str,
        ruta_salida: str = "",
        escala_final: float = ESCALA_FINAL_DEFECTO,
        modelo: str = MODELO_REALESRGAN_DEFECTO,
    ) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                _mejorar_ortofoto_local_sync,
                ruta_imagen_original,
                ruta_salida,
                escala_final,
                modelo,
            )
        except Exception as exc:
            return {"error": str(exc)}
