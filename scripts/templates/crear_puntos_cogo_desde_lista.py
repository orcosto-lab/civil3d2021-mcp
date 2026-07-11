"""
Crea puntos COGO en Civil 3D a partir de una lista de coordenadas.
VARIABLES A RELLENAR: puntos_cogo
CRITICO: orden VARIANT es [Este, Norte, Elevacion] — NO invertir X/Y.
CRITICO: usar GetActiveObject + GetInterfaceObject, nunca Dispatch.
"""
import win32com.client
import pythoncom as pc

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
# Cada entrada: (numero_punto, este, norte, elevacion, descripcion)
# numero_punto=None -> Civil 3D asigna el numero automaticamente
puntos_cogo = [
    (None, 500100.000, 4000200.000, 350.500, "TN"),
    (None, 500150.000, 4000250.000, 352.100, "TN"),
    (None, 500200.000, 4000300.000, 354.300, "EJE"),
]
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   puntos_cogo = [(None, 500100.0, 4000200.0, 350.5, "TN")]
#   -> crea un punto COGO en Este=500100, Norte=4000200, Elev=350.5, desc="TN"

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    # GetInterfaceObject es OBLIGATORIO para acceder a Points de Civil 3D
    civil = acad.GetInterfaceObject("AeccXUiLand.AeccApplication.13.3")
    doc_civil = civil.ActiveDocument
    points_col = doc_civil.Points

    for entrada in puntos_cogo:
        _numero, este, norte, elev, desc = entrada
        try:
            # CRITICO: el array VARIANT debe ir en orden [Este(X), Norte(Y), Elevacion(Z)]
            coords = win32com.client.VARIANT(pc.VT_ARRAY | pc.VT_R8, [este, norte, elev])
            pt = points_col.Add(coords)
            pt.RawDescription = desc
            print(
                f"Punto creado: #{pt.Number}  "
                f"E={pt.Easting:.3f}  N={pt.Northing:.3f}  Z={pt.Elevation:.3f}  "
                f"Desc='{desc}'"
            )
        except Exception as e_pt:
            print(f"Error creando punto (E={este}, N={norte}): {e_pt}")

except Exception as e:
    print(f"Error de conexion con Civil 3D: {e}")
