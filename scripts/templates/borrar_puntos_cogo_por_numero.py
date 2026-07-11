"""
Borra puntos COGO de Civil 3D por su numero de punto.
VARIABLES A RELLENAR: numeros_a_borrar
CRITICO: usar GetActiveObject + GetInterfaceObject, nunca Dispatch.
"""
import win32com.client

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
numeros_a_borrar = [101, 102, 103]   # Lista de numeros de punto COGO a borrar
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   numeros_a_borrar = [5, 10, 15]  -> borra los puntos COGO 5, 10 y 15

try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    civil = acad.GetInterfaceObject("AeccXUiLand.AeccApplication.13.3")
    doc_civil = civil.ActiveDocument
    points_col = doc_civil.Points

    for num in numeros_a_borrar:
        try:
            pt = points_col.Find(num)
            if pt is not None:
                pt.Erase()
                print(f"Punto COGO #{num} borrado.")
            else:
                print(f"Punto COGO #{num} no encontrado.")
        except Exception as e_pt:
            print(f"Error borrando punto #{num}: {e_pt}")

except Exception as e:
    print(f"Error de conexion con Civil 3D: {e}")
