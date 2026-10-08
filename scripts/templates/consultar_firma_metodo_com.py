# consultar_firma_metodo_com.py
# Devuelve la FIRMA EXACTA (nombre de cada parametro y su tipo) de los metodos COM
# de Civil 3D cuyo nombre contenga el termino buscado.
#
# SOLO LECTURA: lee las typelib registradas en HKEY_CLASSES_ROOT\TypeLib. No abre
# Civil 3D, no necesita que este arrancado, no toca ningun dibujo.
#
# Para que sirve: responde de una vez "existe este metodo en la API COM legacy y
# que le tengo que pasar", que es la pregunta que ha frenado varias tools de este
# proyecto. La documentacion oficial de Autodesk NO indexa la API ActiveX legacy.
#
# LECCION IMPORTANTE: los metodos sobrecargados aparecen NUMERADOS en la typelib
# (AddFixedLine1/2/3, AddFixedCurve1..8). Buscar el nombre exacto sin numero no
# encuentra nada y lleva a concluir en falso que el metodo "no existe en COM".
# Buscar siempre por prefijo: "AddFixed", no "AddFixedLine".
#
# Uso:  python -B consultar_firma_metodo_com.py <termino_parcial>
# Ej.:  python -B consultar_firma_metodo_com.py AddFreeSymmetricParabola

import sys
import winreg

import pythoncom

VT = {2: "int16", 3: "int32", 4: "single", 5: "double", 7: "date", 8: "BSTR",
      9: "IDispatch", 11: "bool", 12: "VARIANT", 13: "IUnknown", 17: "uint8",
      19: "uint32", 22: "int", 23: "uint", 24: "void", 26: "ptr",
      29: "enum/userdef", 8192: "ARRAY", 16384: "BYREF"}


def tipo(t) -> str:
    """Traduce un descriptor de tipo de la typelib a algo legible."""
    base = t[0] if isinstance(t, tuple) else t
    if isinstance(base, tuple):
        return tipo(base)
    n = base & 0x0FFF
    s = VT.get(n, "vt%s" % n)
    if base & 16384:
        s += "*"          # parametro por referencia (necesita VARIANT BYREF)
    if base & 8192:
        s = "array<%s>" % s
    return s


def typelibs(filtro: str = "aecc"):
    out = []
    root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TypeLib")
    i = 0
    while True:
        try:
            g = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        try:
            gk = winreg.OpenKey(root, g)
        except OSError:
            continue
        j = 0
        while True:
            try:
                v = winreg.EnumKey(gk, j)
            except OSError:
                break
            j += 1
            try:
                nom = winreg.QueryValue(winreg.OpenKey(gk, v), None)
            except OSError:
                nom = ""
            if filtro in nom.lower():
                out.append((nom, g, v))
    return out


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -B consultar_firma_metodo_com.py <termino_parcial>")
        raise SystemExit(1)
    termino = sys.argv[1].lower()
    hallazgos = 0

    for nom, g, v in typelibs():
        try:
            # version en HEXADECIMAL en el registro (2021 = "d.3")
            ma, mi = v.split(".")
            tlb = pythoncom.LoadRegTypeLib(g, int(ma, 16), int(mi, 16), 0)
        except Exception:
            continue
        for k in range(tlb.GetTypeInfoCount()):
            try:
                ti = tlb.GetTypeInfo(k)
                attr = ti.GetTypeAttr()
                tname = tlb.GetDocumentation(k)[0]
            except Exception:
                continue
            for f in range(attr.cFuncs):
                try:
                    fd = ti.GetFuncDesc(f)
                    nombres = ti.GetNames(fd.memid)
                except Exception:
                    continue
                if termino not in nombres[0].lower():
                    continue
                hallazgos += 1
                params = []
                for idx, a in enumerate(fd.args):
                    pn = nombres[idx + 1] if idx + 1 < len(nombres) else "arg%d" % idx
                    params.append("%s: %s" % (pn, tipo(a)))
                print("%s :: %s.%s(%s) -> %s"
                      % (nom, tname, nombres[0], ", ".join(params), tipo(fd.rettype)))

    if hallazgos == 0:
        print("Sin resultados para '%s'." % termino)
        print("Recuerda: los metodos sobrecargados van numerados (AddFixedCurve1..8).")
        print("Prueba con un prefijo mas corto.")


if __name__ == "__main__":
    main()
