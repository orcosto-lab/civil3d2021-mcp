"""
Borra un objeto de Civil 3D / AutoCAD por su handle.
VARIABLES A RELLENAR: handle_objetivo
"""
import win32com.client

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
handle_objetivo = "1A3F"   # Handle hex del objeto (visible en Propiedades > Handle)
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   handle_objetivo = "1A3F"  -> borra el objeto con handle 0x1A3F del ModelSpace

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument
    obj = doc.HandleToObject(handle_objetivo)
    nombre = obj.ObjectName
    obj.Delete()
    print(f"Objeto '{nombre}' (handle {handle_objetivo}) borrado correctamente.")
except Exception as e:
    print(f"Error al borrar objeto (handle {handle_objetivo}): {e}")
