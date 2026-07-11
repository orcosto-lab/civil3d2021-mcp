"""
Crea un circulo en el ModelSpace de Civil 3D / AutoCAD.
VARIABLES A RELLENAR: este, norte, elevacion, radio, capa
"""
import win32com.client
import pythoncom as pc

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
este      = 500000.0   # Coordenada X (Este)  del centro
norte     = 4000000.0  # Coordenada Y (Norte) del centro
elevacion = 0.0        # Coordenada Z (Elevacion) del centro
radio     = 10.0       # Radio del circulo (unidades del dibujo)
capa      = "0"        # Capa destino (debe existir en el dibujo)
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   este=500100.0, norte=4000200.0, elevacion=350.0, radio=5.0, capa="TOPOGRAFIA"
#   -> crea un circulo de r=5 centrado en ese punto en la capa TOPOGRAFIA

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument
    ms = doc.ModelSpace

    centro = win32com.client.VARIANT(pc.VT_ARRAY | pc.VT_R8, [este, norte, elevacion])
    circulo = ms.AddCircle(centro, radio)
    circulo.Layer = capa
    doc.Regen(1)  # acRegenAll
    print(f"Circulo creado: centro=({este}, {norte}, {elevacion}), radio={radio}, capa='{capa}'")
    print(f"  Handle: {circulo.Handle}")
except Exception as e:
    print(f"Error al crear circulo: {e}")
