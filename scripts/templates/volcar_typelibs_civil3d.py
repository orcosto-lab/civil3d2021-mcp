# volcar_typelibs_civil3d.py
# Vuelca a JSON los ENUMS y COCLASES de todas las type libraries de Civil 3D
# (familia Aecc*) registradas en el sistema.
#
# SOLO LECTURA: no abre Civil 3D, no necesita que este arrancado, no toca ningun
# dibujo. Lee las typelib declaradas en HKEY_CLASSES_ROOT\TypeLib.
#
# Para que sirve: la API COM legacy de Civil 3D no esta indexada en el buscador de
# ayuda de Autodesk. Los valores de los enums (AeccProfileType, AeccSag/Crest...) y
# si un objeto se puede instanciar desde fuera (AeccStationRange,
# AeccPointImportOptions...) SOLO se pueden averiguar leyendo la typelib. Esto lo
# automatiza, en vez de mirarlo a mano en el Object Browser de VBA (Alt+F11).
#
# Salida por defecto: <raiz_proyecto>\referencia\typelibs_civil3d_2021.json
# Consultarla despues con consultar_enum_com.py.
#
# Uso:  python -B volcar_typelibs_civil3d.py [ruta_salida.json]

import json
import sys
import winreg
from pathlib import Path

import pythoncom

RAIZ = Path(__file__).resolve().parents[2]
SALIDA_DEFECTO = RAIZ / "referencia" / "typelibs_civil3d_2021.json"


def listar_typelibs(filtro: str = "aecc"):
    """Devuelve [(nombre, guid, version)] de las typelib registradas que casen."""
    encontradas = []
    root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TypeLib")
    i = 0
    while True:
        try:
            guid = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        try:
            gk = winreg.OpenKey(root, guid)
        except OSError:
            continue
        j = 0
        while True:
            try:
                ver = winreg.EnumKey(gk, j)
            except OSError:
                break
            j += 1
            try:
                nombre = winreg.QueryValue(winreg.OpenKey(gk, ver), None)
            except OSError:
                nombre = ""
            if filtro in nombre.lower():
                encontradas.append((nombre, guid, ver))
    return encontradas


def volcar(nombre: str, guid: str, ver: str) -> dict:
    """Carga una typelib y extrae sus enums, coclases e interfaces."""
    try:
        # OJO: la version de la typelib viene en HEXADECIMAL en el registro
        # (Civil 3D 2021 = "d.3", no "13.3"). int(x, 16) es obligatorio.
        major, minor = ver.split(".")
        tlb = pythoncom.LoadRegTypeLib(guid, int(major, 16), int(minor, 16), 0)
    except Exception as e:
        return {"lib": nombre, "version": ver, "error": str(e)}

    enums, coclases, interfaces = {}, [], []
    for k in range(tlb.GetTypeInfoCount()):
        try:
            tipo = tlb.GetTypeInfoType(k)
            tname = tlb.GetDocumentation(k)[0]
            ti = tlb.GetTypeInfo(k)
            attr = ti.GetTypeAttr()
        except Exception:
            continue
        if tipo == pythoncom.TKIND_ENUM:
            miembros = {}
            for v in range(attr.cVars):
                try:
                    vd = ti.GetVarDesc(v)
                    miembros[ti.GetNames(vd.memid)[0]] = vd.value
                except Exception:
                    pass
            enums[tname] = miembros
        elif tipo == pythoncom.TKIND_COCLASS:
            # TYPEFLAG_FCANCREATE = se puede instanciar desde un proceso externo
            # (win32com.client.Dispatch). Si es False, solo se obtiene a traves de
            # otro objeto COM, nunca creandolo directamente.
            creable = bool(attr.wTypeFlags & pythoncom.TYPEFLAG_FCANCREATE)
            coclases.append({"nombre": tname, "creable": creable})
        elif tipo in (pythoncom.TKIND_INTERFACE, pythoncom.TKIND_DISPATCH):
            interfaces.append(tname)

    return {
        "lib": nombre,
        "version": ver,
        "guid": guid,
        "enums": enums,
        "coclases": coclases,
        "interfaces": interfaces,
    }


def main() -> None:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SALIDA_DEFECTO
    libs = listar_typelibs("aecc")
    print("Typelibs Aecc registradas: %d" % len(libs))
    for n, g, v in libs:
        print("  - %-45s ver %-5s %s" % (n, v, g))

    salida = [volcar(n, g, v) for (n, g, v) in libs]
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=1, ensure_ascii=False)

    print("\nEscrito: %s" % destino)
    for s in salida:
        if "error" in s:
            print("  ERROR %-45s %s" % (s["lib"], s["error"]))
        else:
            print("  %-45s %4d enums  %4d coclases  %4d interfaces"
                  % (s["lib"], len(s["enums"]), len(s["coclases"]), len(s["interfaces"])))


if __name__ == "__main__":
    main()
