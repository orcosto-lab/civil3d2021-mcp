"""
client.py  -  Cliente COM para Civil 3D / AutoCAD
Gestiona la conexion via pywin32 (win32com.client)
La conexion se establece de forma lazy en cada llamada.
"""
from __future__ import annotations
import logging
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
