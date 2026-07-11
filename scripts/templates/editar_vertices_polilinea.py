"""
Reemplaza los vertices de una polilinea 2D o 3D identificada por handle.
VARIABLES A RELLENAR: handle_polilinea, nuevos_vertices
"""
import win32com.client
import pythoncom as pc

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
handle_polilinea = "1A3F"   # Handle hex de la polilinea a editar

# Lista de (este, norte, elevacion) — REEMPLAZA todos los vertices existentes
nuevos_vertices = [
    (500000.0, 4000000.0, 350.0),
    (500100.0, 4000050.0, 351.0),
    (500200.0, 4000100.0, 352.0),
    (500300.0, 4000150.0, 353.0),
]
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   handle_polilinea = "2B10"
#   nuevos_vertices = [(500000.0, 4000000.0, 0.0), (500100.0, 4000100.0, 0.0)]
#   -> reemplaza los vertices de la polilinea 2B10 con los dos puntos dados

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument

    pline = doc.HandleToObject(handle_polilinea)
    tipo = pline.ObjectName
    print(f"Objeto encontrado: {tipo} (handle {handle_polilinea})")

    if "3d" in tipo.lower() or tipo == "AcDb3dPolyline":
        # Polilinea 3D: array plano [x0, y0, z0, x1, y1, z1, ...]
        coords_flat = []
        for (este, norte, elev) in nuevos_vertices:
            coords_flat.extend([este, norte, elev])
        pline.Coordinates = win32com.client.VARIANT(pc.VT_ARRAY | pc.VT_R8, coords_flat)
    else:
        # Polilinea 2D / LW: array plano [x0, y0, x1, y1, ...]
        coords_flat = []
        for (este, norte, _elev) in nuevos_vertices:
            coords_flat.extend([este, norte])
        pline.Coordinates = win32com.client.VARIANT(pc.VT_ARRAY | pc.VT_R8, coords_flat)

    doc.Regen(1)
    print(f"Vertices actualizados: {len(nuevos_vertices)} puntos.")
except Exception as e:
    print(f"Error al editar vertices de polilinea: {e}")
