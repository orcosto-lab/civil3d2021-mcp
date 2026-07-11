"""
Cambia la capa de uno o varios objetos identificados por su handle.
VARIABLES A RELLENAR: handles_y_capas
"""
import win32com.client

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
# Lista de tuplas (handle_hex, nueva_capa). La capa debe existir en el dibujo.
handles_y_capas = [
    ("1A3F", "TOPOGRAFIA"),
    ("2B10", "EJES"),
    ("3C22", "0"),
]
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   handles_y_capas = [("1A3F", "TOPOGRAFIA")]
#   -> cambia el objeto con handle 1A3F a la capa TOPOGRAFIA

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument

    for handle, nueva_capa in handles_y_capas:
        try:
            obj = doc.HandleToObject(handle)
            capa_anterior = obj.Layer
            obj.Layer = nueva_capa
            print(f"Handle {handle}: capa '{capa_anterior}' -> '{nueva_capa}'")
        except Exception as e_inner:
            print(f"Handle {handle}: error -> {e_inner}")

    doc.Regen(1)
except Exception as e:
    print(f"Error de conexion con AutoCAD: {e}")
