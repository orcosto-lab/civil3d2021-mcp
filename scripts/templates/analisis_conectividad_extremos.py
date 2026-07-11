"""
Analiza la conectividad de extremos entre polilineas en el ModelSpace.
Detecta extremos libres (no conectados) y pares que se tocan dentro de tolerancia.
VARIABLES A RELLENAR: tolerancia, capas_filtro
"""
import win32com.client
import math

# ── VARIABLES A RELLENAR ─────────────────────────────────────────────────────
tolerancia   = 0.001   # Distancia maxima (unidades dibujo) para considerar conectados
capas_filtro = []      # Capas a analizar; [] = todas las capas del dibujo
# ─────────────────────────────────────────────────────────────────────────────

# Ejemplo de uso:
#   tolerancia = 0.01, capas_filtro = ["EJES", "TOPOGRAFIA"]
#   -> reporta extremos libres y pares conectados solo en esas capas

TIPOS_POLILINEA = {"AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline", "AcDbLwPolyline"}


def distancia_3d(p1, p2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def extremos_de(obj):
    """Devuelve (inicio, fin) como tuplas (x, y, z), o (None, None) si falla."""
    try:
        coords = list(obj.Coordinates)
        if len(coords) >= 6 and len(coords) % 3 == 0:
            return tuple(coords[:3]), tuple(coords[-3:])
        if len(coords) >= 4 and len(coords) % 2 == 0:
            return (coords[0], coords[1], 0.0), (coords[-2], coords[-1], 0.0)
    except Exception:
        pass
    return None, None


try:
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc = acad.ActiveDocument
    ms = doc.ModelSpace

    plines = []
    for obj in ms:
        try:
            if obj.ObjectName not in TIPOS_POLILINEA:
                continue
            if capas_filtro and obj.Layer not in capas_filtro:
                continue
            inicio, fin = extremos_de(obj)
            if inicio is not None:
                plines.append({
                    "handle": obj.Handle,
                    "capa":   obj.Layer,
                    "inicio": inicio,
                    "fin":    fin,
                })
        except Exception:
            continue

    print(f"\nPolilineas analizadas: {len(plines)}")

    # Construir lista plana de extremos
    extremos = []
    for pl in plines:
        extremos.append({"handle": pl["handle"], "capa": pl["capa"],
                         "tipo": "inicio", "punto": pl["inicio"]})
        extremos.append({"handle": pl["handle"], "capa": pl["capa"],
                         "tipo": "fin",    "punto": pl["fin"]})

    # Detectar pares conectados
    conectados = set()
    pares = []
    for i in range(len(extremos)):
        for j in range(i + 1, len(extremos)):
            if extremos[i]["handle"] == extremos[j]["handle"]:
                continue  # mismo objeto, ignorar
            d = distancia_3d(extremos[i]["punto"], extremos[j]["punto"])
            if d <= tolerancia:
                conectados.add(i)
                conectados.add(j)
                pares.append((extremos[i], extremos[j], d))

    libres = [e for idx, e in enumerate(extremos) if idx not in conectados]

    print(f"\nPares conectados (dist <= {tolerancia}): {len(pares)}")
    for a, b, d in pares:
        print(f"  {a['handle']} ({a['tipo']}) <-> {b['handle']} ({b['tipo']})  dist={d:.4f}")

    print(f"\nExtremos libres (sin conexion): {len(libres)}")
    for e in libres:
        p = e["punto"]
        print(f"  Handle {e['handle']}  {e['tipo']}  ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})  capa='{e['capa']}'")

except Exception as e:
    print(f"Error de conexion con AutoCAD: {e}")
