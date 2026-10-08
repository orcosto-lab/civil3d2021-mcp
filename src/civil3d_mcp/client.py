"""
client.py  -  Cliente COM para Civil 3D / AutoCAD
Gestiona la conexion via pywin32 (win32com.client)
La conexion se establece de forma lazy en cada llamada.
"""
from __future__ import annotations
import logging
import time
import pythoncom
import win32com.client

log = logging.getLogger("civil3d_mcp.client")


class Civil3DError(Exception):
    pass


class Civil3DClient:
    """
    Wrapper sobre la conexion COM a Civil 3D.
    La conexion es lazy: se establece en la primera llamada real.
    - _acad  : objeto AutoCAD.Application
    - _doc   : AeccDocument de Civil 3D (superficies, alineaciones, puntos COGO)
    """

    def __init__(self):
        self._acad = None
        self._doc = None

    def _connect(self):
        try:
            pythoncom.CoInitialize()
            self._acad = win32com.client.GetActiveObject("AutoCAD.Application")
            log.info(f"Conectado a: {self._acad.Name} {self._acad.Version}")
            self._try_connect_civil3d()
        except Exception as exc:
            self._acad = None
            raise Civil3DError(f"No se pudo conectar a AutoCAD COM: {exc}")

    def _try_connect_civil3d(self):
        try:
            civil_app = self._acad.GetInterfaceObject("AeccXUiLand.AeccApplication.13.3")
            self._doc = civil_app.ActiveDocument
            log.info("Civil 3D conectado via AeccXUiLand.AeccApplication.13.3")
            return
        except Exception as exc:
            log.warning(f"Civil 3D no disponible via COM ({exc}), usando solo AutoCAD base")
        self._doc = None

    def _get_acad(self):
        if self._acad is None:
            self._connect()
        return self._acad

    def _get_cogo_collection(self):
        """
        Devuelve la coleccion de puntos COGO.
        Fallback: escanea ModelSpace si la coleccion COM falla.
        """
        if self._doc is None:
            log.warning("AeccDocument no disponible, usando fallback ModelSpace")
            return None
        try:
            points = self._doc.Points
            _ = points.Count
            return points
        except Exception as exc:
            log.warning(f"Points COM fallo ({exc}), usando fallback ModelSpace")
            return None

    @property
    def active_doc(self):
        acad = self._get_acad()
        try:
            return acad.ActiveDocument
        except Exception as exc:
            raise Civil3DError(f"No hay documento activo en Civil 3D: {exc}")

    @property
    def model_space(self):
        return self.active_doc.ModelSpace


# ---------------------------------------------------------------------------
# Helpers reutilizables para tools_*.py
# ---------------------------------------------------------------------------

def iter_com_collection(col):
    """
    Itera una coleccion COM de Civil 3D de forma defensiva.
    Prueba, en orden: Item(i) 0-based, Item(i) 1-based, iteracion for cruda.
    Motivo: algunas colecciones de Civil 3D fallan de forma silenciosa con un
    metodo de acceso pero funcionan con otro (ya vistos bugs reales del
    proyecto de "exito reportado sin accion real" en otras colecciones).
    Devuelve siempre una lista de objetos COM, nunca la coleccion original.
    """
    if col is None:
        return []
    items = []
    try:
        count = int(col.Count)
    except Exception as exc:
        log.debug("iter_com_collection: no se pudo leer Count: %s", exc)
        count = -1

    if count > 0:
        cero = []
        for i in range(count):
            try:
                cero.append(col.Item(i))
            except Exception:
                break
        if len(cero) == count:
            return cero

        uno = []
        for i in range(1, count + 1):
            try:
                uno.append(col.Item(i))
            except Exception:
                break
        if len(uno) == count:
            return uno

        mejor = cero if len(cero) >= len(uno) else uno
        if mejor:
            log.debug(
                "iter_com_collection: devolviendo resultado parcial (%d/%d)",
                len(mejor), count,
            )
            return mejor

    try:
        for item in col:
            items.append(item)
    except Exception as exc:
        log.debug("iter_com_collection: iteracion for cruda fallo: %s", exc)

    if not items and count > 0:
        log.warning(
            "iter_com_collection: Count=%d pero todas las estrategias de "
            "iteracion fallaron.", count,
        )
    return items


def variant_out_double():
    """
    Construye un VARIANT VT_R8|VT_BYREF para parametros COM de salida por
    referencia (ej. Alignment.StationOffset). Un float normal de Python es
    inmutable: Civil 3D no puede escribir el resultado en el, y el valor de
    salida queda siempre en 0.0 sin dar ningun error.
    """
    return win32com.client.VARIANT(pythoncom.VT_R8 | pythoncom.VT_BYREF, 0.0)


# HRESULT de RPC_E_CALL_REJECTED. Civil 3D es una app STA: un unico hilo
# atiende su interfaz Y las llamadas COM entrantes. Si ese hilo esta ocupado
# un instante (autoguardado, comprobacion de variables de sistema, redibujado),
# cualquier llamada COM externa que llegue justo entonces recibe este error.
# No es un dialogo colgado ni un bug de la tool que lo sufre -- es contencion
# transitoria de la arquitectura COM de AutoCAD. Confirmado en vivo 07/09/2026:
# el mismo error aparecia en llamadas identicas repetidas segundos despues,
# coincidiendo con un autoguardado visible en leer_historial_comandos.
RPC_CALL_REJECTED = "-2147418111"


def forzar_escape_civil3d(client, intentos_foco: int = 3, espera_foco: float = 0.15) -> dict:
    """
    Pulsacion de Escape REAL a nivel de sistema operativo sobre la ventana de
    AutoCAD/Civil 3D -- para liberar la consola cuando un comando enviado via
    SendCommand se queda colgado esperando seleccion (p.ej. EXPLODE en
    "Designe objeto:"). LECCION (28/09/2026): un caracter ESC dentro de la
    propia cadena de SendCommand NO sirve -- SendCommand rechaza la llamada
    entera con "Entrada no valida" (COM exception sincrona), tanto suelto como
    pegado al final de un comando completo. Solo una pulsacion de teclado real
    (a nivel de Windows, no de COM) libera la consola -- confirmado en pruebas
    reales con Pedro pulsando Escape manualmente.

    Usa Application.HWND (ventana principal de AutoCAD), NO Document.HWND
    (puede ser un MDI child interno, menos fiable para SetForegroundWindow).
    SIEMPRE verifica que el foco realmente cambio antes de mandar la tecla --
    SetForegroundWindow puede fallar en silencio por restricciones del propio
    Windows (mismo problema ya documentado en el wiki para MCPControl/
    computer-use: "no fiarse de que una accion de cambio de foco/ventana hizo
    lo que su nombre sugiere sin verificarlo"). Si no se puede confirmar el
    foco, NO se envia ninguna tecla (mejor no hacer nada que pulsar Escape en
    la ventana equivocada).

    Reutilizable desde cualquier tool que dependa de SendCommand y pueda
    toparse con un prompt de seleccion colgado -- no es exclusivo de
    explotar_objeto/explotar_por_handle.

    LECCION (28/09/2026): win32gui.SetForegroundWindow "a pelo" puede fallar
    con WinError 0 ("No error message is available") por el "foreground lock"
    de Windows -- un proceso en segundo plano (como este servidor MCP) no
    puede robar el primer plano salvo que cumpla ciertas condiciones (haber
    recibido input reciente, ser el mismo hilo que la ventana activa, etc.).
    Confirmado en vivo: fallo real durante una prueba con Pedro delante de la
    pantalla, dejando el EXPLODE colgado sin liberar. Arreglo: adjuntar la
    cola de entrada del hilo actual a la del hilo de la ventana en primer
    plano via AttachThreadInput (tecnica estandar de la Win32 API para este
    caso, documentada por Microsoft) antes de llamar a SetForegroundWindow;
    se desadjunta siempre en el finally, incluso si algo falla a medias.
    """
    import ctypes
    import win32gui
    import win32con
    import win32api

    try:
        acad = client._get_acad()
        hwnd = acad.HWND
    except Exception as exc:
        return {"error": f"No se pudo obtener HWND de la aplicacion Civil3D/AutoCAD: {exc}"}

    if not hwnd:
        return {"error": "Application.HWND vacio o invalido."}

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception as exc:
        return {"error": f"ShowWindow/IsIconic fallo (hwnd={hwnd}): {exc}"}

    fg_hwnd = user32.GetForegroundWindow()
    current_tid = kernel32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

    attached_fg = False
    attached_target = False
    try:
        if fg_tid and fg_tid != current_tid:
            attached_fg = bool(user32.AttachThreadInput(current_tid, fg_tid, True))
        if target_tid and target_tid != current_tid:
            attached_target = bool(user32.AttachThreadInput(current_tid, target_tid, True))
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            return {"error": f"SetForegroundWindow fallo (hwnd={hwnd}, con AttachThreadInput fg={attached_fg} target={attached_target}): {exc}"}
    finally:
        if attached_target:
            user32.AttachThreadInput(current_tid, target_tid, False)
        if attached_fg:
            user32.AttachThreadInput(current_tid, fg_tid, False)

    foco_confirmado = False
    for _ in range(intentos_foco):
        time.sleep(espera_foco)
        try:
            fg = win32gui.GetForegroundWindow()
        except Exception:
            fg = None
        if fg == hwnd:
            foco_confirmado = True
            break

    if not foco_confirmado:
        return {
            "success": False,
            "hwnd": hwnd,
            "error": (
                "No se pudo confirmar que la ventana de Civil3D/AutoCAD quedo "
                "en primer plano tras SetForegroundWindow (Windows puede "
                "bloquear el cambio de foco). No se ha enviado ninguna tecla "
                "para evitar pulsar Escape en la ventana equivocada."
            ),
        }

    win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)

    return {"success": True, "hwnd": hwnd, "foco_confirmado": True}


def con_reintentos(fn, intentos: int = 6, espera: float = 0.3):
    """
    Ejecuta fn() reintentando SOLO ante RPC_E_CALL_REJECTED; cualquier otro
    error se relanza de inmediato (no es contencion transitoria, es un fallo
    real que hay que ver). LECCION: iterar una coleccion COM grande
    (`for x in col`) hace una llamada COM implicita por cada item; un try/
    except puesto solo en el CUERPO del bucle no cubre un fallo en el propio
    mecanismo de iteracion (`next()`), asi que un unico fallo transitorio a
    mitad de una coleccion de cientos/miles de objetos aborta la llamada
    entera pese a los try/except internos. Hay que envolver la operacion
    COMPLETA (la funcion que hace el bucle) y reintentarla entera, no un
    solo item. La probabilidad de toparse con una ventana ocupada de Civil3D
    crece con el numero de idas y vueltas COM de una sola llamada -- por eso
    esto se nota mas en tools que iteran ModelSpace/Points completos que en
    llamadas sueltas de 2-3 propiedades.
    """
    ultimo = None
    for _ in range(intentos):
        try:
            return fn()
        except Exception as exc:
            ultimo = exc
            if RPC_CALL_REJECTED not in str(exc):
                raise
            time.sleep(espera)
    raise ultimo
