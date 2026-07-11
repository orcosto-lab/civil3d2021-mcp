# acotar_bloque_seccion.py
# Acota con MLeaders de nivel (Z real) un bloque de seccion generado desde un
# plano de seccion. cota = Y_local_bloque + Elevation del plano de seccion.
# Uso: rellenar las variables de CONFIGURACION y ejecutar con el dibujo activo.
#
# Los vertices de la linea de corte NO se pueden leer via COM externo
# (Section.Vertices da "Violacion de bloqueo"). Obtenerlos con este LISP
# in-process (OJO: (load ...) dispara el dialogo SECURELOAD, aceptar):
#   (vl-load-com)
#   (setq o (vlax-ename->vla-object (handent "HANDLE_SECCION")))
#   (setq l (vlax-safearray->list (vlax-variant-value (vla-get-Vertices o))))
#   (setq f (open "C:/MCP/tmp_sec_verts.txt" "w")) (print l f) (close f)

import win32com.client as wc
import pythoncom, math

# ----------------- CONFIGURACION -----------------
SEC_LINEA = ((447812.713839, 4475421.342691),   # (x1, y1) linea de corte en planta
             (447790.652076, 4475411.407461))   # (x2, y2)
ELEV = 657.0                    # Elevation del AcDbSection
BLQ_NOMBRE = "A$Cb56779d6"      # nombre de la definicion del bloque de seccion
BLQ_HANDLE = "19AC"             # handle de la referencia insertada
CAPAS_MODELO = ["01 - Boveda", "02 - Vitrex", "03 - Mecanica",
                "04 - Escalera", "05 - Verticales", "06 - Terminado", "0"]
CAPA_DESTINO = "IA"             # capa de las cotas (se crea en cian si falta)
TOL = 0.02                      # tolerancia casado/dedup (m)
DIRECTRIZ = 0.5                 # largo del tramo vertical del MLeader (m)
DECIMALES = 3
ALTURA_TEXTO = 0.2
# --------------------------------------------------

pythoncom.CoInitialize()
acad = wc.GetActiveObject("AutoCAD.Application")  # NUNCA Dispatch
doc = acad.ActiveDocument
print("Dibujo:", doc.Name)

# --- aristas 3D del modelo ---
aristas = []
for raw in doc.ModelSpace:
    try:
        obj = wc.Dispatch(raw)
        on, cl = obj.ObjectName, obj.Layer
        if cl not in CAPAS_MODELO:
            continue
        if on == "AcDbLine":
            aristas.append((tuple(obj.StartPoint), tuple(obj.EndPoint)))
        elif on == "AcDb3dPolyline":
            c = list(obj.Coordinates)
            pts = [(c[i], c[i+1], c[i+2]) for i in range(0, len(c), 3)]
            aristas += [(pts[i], pts[i+1]) for i in range(len(pts)-1)]
    except Exception:
        pass
print("Aristas modelo:", len(aristas))

(ax, ay), (bx, by) = SEC_LINEA
dx, dy = bx-ax, by-ay
L = math.hypot(dx, dy)

def cruce(p, q):
    ex, ey = q[0]-p[0], q[1]-p[1]
    den = dx*ey - dy*ex
    if abs(den) < 1e-12:
        return None
    t = ((ax-p[0])*dy - (ay-p[1])*dx) / (-den)
    if t < -1e-9 or t > 1+1e-9:
        return None
    cx, cy = p[0]+t*ex, p[1]+t*ey
    s = ((cx-ax)*dx + (cy-ay)*dy) / (L*L)
    if s < -1e-9 or s > 1+1e-9:
        return None
    return (s*L, p[2] + t*(q[2]-p[2]))

puntos = [r for p, q in aristas if (r := cruce(p, q)) is not None]
puntos.sort()
dedup = []
for d, z in puntos:
    if not any(abs(d-d0) < TOL and abs(z-z0) < TOL for d0, z0 in dedup):
        dedup.append((d, z))
print(f"Intersecciones: {len(puntos)} -> dedup: {len(dedup)}")

# --- vertices locales del bloque y calibracion X (local_x = dir*d + offset) ---
bdef = doc.Blocks.Item(BLQ_NOMBRE)
vtx = []
for raw in bdef:
    obj = wc.Dispatch(raw)
    if obj.ObjectName == "AcDbLine":
        sp, ep = obj.StartPoint, obj.EndPoint
        vtx += [(sp[0], sp[1]), (ep[0], ep[1])]

mejor = None
for dr in (1, -1):
    cands = {}
    for d, z in dedup:
        yl = z - ELEV
        for x, y in vtx:
            if abs(y - yl) < TOL:
                k = round((x - dr*d) / TOL)
                cands[k] = cands.get(k, 0) + 1
    if cands:
        k, score = max(cands.items(), key=lambda kv: kv[1])
        if mejor is None or score > mejor[2]:
            mejor = (dr, k*TOL, score)
dr, off, _ = mejor
difs = sorted(x - dr*d for d, z in dedup for x, y in vtx
              if abs(y-(z-ELEV)) < TOL and abs((x-dr*d)-off) < 3*TOL)
if difs:
    off = difs[len(difs)//2]
ok = sum(1 for d, z in dedup
         if any(abs(y-(z-ELEV)) < TOL and abs(x-(dr*d+off)) < TOL for x, y in vtx))
print(f"Calibracion: dir={dr} offset={off:.4f} | casados {ok}/{len(dedup)}")
assert ok / len(dedup) >= 0.8, "Casado <80%: revisar seccion/bloque antes de acotar"

# --- capa destino y creacion de MLeaders ---
try:
    existia = any(l.Name == CAPA_DESTINO for l in doc.Layers)
    capa = doc.Layers.Add(CAPA_DESTINO)
    if not existia:
        capa.Color = 4
except Exception as e:
    print("Capa:", e)

ref = wc.Dispatch(doc.HandleToObject(BLQ_HANDLE))
ins = list(ref.InsertionPoint)
sx = ref.XScaleFactor            # -1 en vistas especulares
ys_loc = [z - ELEV for d, z in dedup]
mid = (min(ys_loc) + max(ys_loc)) / 2.0
ms = doc.ModelSpace
for d, z in dedup:
    lx, ly = dr*d + off, z - ELEV
    wx, wy, wz = ins[0] + sx*lx, ins[1] + ly, ins[2]
    up = 1.0 if ly >= mid else -1.0
    pts = wc.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                     [wx, wy, wz, wx, wy + up*DIRECTRIZ, wz])
    try:
        ret = ms.AddMLeader(pts, 0)
        ml = ret[0] if isinstance(ret, tuple) else ret  # pywin32: (objeto, indice)
        try:
            ml.ContentType = 2
        except Exception:
            pass
        ml.TextString = f"{z:.{DECIMALES}f}"
        try:
            ml.TextHeight = ALTURA_TEXTO
        except Exception:
            pass
        ml.Layer = CAPA_DESTINO
        print(f"  h={ml.Handle} | d={d:8.3f} | cota={z:.{DECIMALES}f}")
    except Exception as e:
        print(f"  ERROR d={d:.3f} z={z:.3f}: {e}")
