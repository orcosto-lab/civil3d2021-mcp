"""
Copia un objeto identificado por handle aplicando un vector de desplazamiento.
VARIABLES A RELLENAR: handle_origen, dx, dy, dz, capa_destino
"""
import win32com.client
import pythoncom as pc

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
handle_origen = "1A3F"   # Handle hex del objeto a copiar
dx            = 10.0     # Desplazamiento en X (Este),      en unidades del dibujo
dy            = 0.0      # Desplazamiento en Y (Norte),     en unidades del dibujo
dz            = 0.0      # Desplazamiento en Z (Elevacion), en unidades del dibujo
capa_destino  = ""       # Capa de la copia ("" = conservar la del original)
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   handle_origen="1A3F", dx=50.0, dy=0.0, dz=0.0, capa_destino="COPIA"
#   -> duplica el objeto y lo desplaza 50 m al Este asignandolo a la capa COPIA

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument

    obj_origen = doc.HandleToObject(handle_origen)

    # Move requiere dos puntos: base (origen) y destino; el desplazamiento es la diferencia
    pto_base    = win32com.client.VARIANT(pc.VT_ARRAY | pc.VT_R8, [0.0, 0.0, 0.0])
    pto_destino = win32com.client.VARIANT(pc.VT_ARRAY | pc.VT_R8, [dx, dy, dz])

    copia = obj_origen.Copy()
    copia.Move(pto_base, pto_destino)

    if capa_destino:
        copia.Layer = capa_destino

    doc.Regen(1)
    print(f"Objeto (handle {handle_origen}) copiado -> handle copia: {copia.Handle}")
    print(f"  Desplazamiento: dx={dx}, dy={dy}, dz={dz}")
    if capa_destino:
        print(f"  Capa asignada: '{capa_destino}'")
except Exception as e:
    print(f"Error al copiar objeto: {e}")
