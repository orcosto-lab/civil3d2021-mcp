# consultar_enum_com.py
# Busca un ENUM o una COCLASE de Civil 3D por nombre (subcadena, sin distinguir
# mayusculas) en el volcado JSON generado por volcar_typelibs_civil3d.py.
#
# SOLO LECTURA sobre un archivo local: no toca Civil 3D ni el registro.
#
# Responde a dos preguntas que han bloqueado varias tools de este proyecto:
#   1. "Que valor entero le paso a este parametro de tipo enum?"
#        -> python -B consultar_enum_com.py profiletype
#   2. "Puedo crear este objeto desde Python con Dispatch, o solo desde VBA?"
#        -> python -B consultar_enum_com.py importoptions      (mira creable=True/False)
#
# Uso:  python -B consultar_enum_com.py <termino> [ruta_json]

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JSON_DEFECTO = RAIZ / "referencia" / "typelibs_civil3d_2021.json"


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -B consultar_enum_com.py <termino> [ruta_json]")
        raise SystemExit(1)

    termino = sys.argv[1].lower()
    ruta = Path(sys.argv[2]) if len(sys.argv) > 2 else JSON_DEFECTO
    if not ruta.exists():
        print("No existe %s\nGeneralo con: python -B volcar_typelibs_civil3d.py" % ruta)
        raise SystemExit(1)

    datos = json.load(open(ruta, encoding="utf-8"))
    hallazgos = 0

    for lib in datos:
        if "error" in lib:
            continue
        for nombre, miembros in lib.get("enums", {}).items():
            if termino in nombre.lower():
                hallazgos += 1
                print("[ENUM] %s :: %s" % (lib["lib"], nombre))
                for k, v in sorted(miembros.items(), key=lambda x: x[1]):
                    print("    %-45s = %s" % (k, v))
        for c in lib.get("coclases", []):
            if termino in c["nombre"].lower():
                hallazgos += 1
                print("[COCLASE] %s :: %-40s creable=%s"
                      % (lib["lib"], c["nombre"], c["creable"]))

    if hallazgos == 0:
        print("Sin resultados para '%s'." % termino)
        print("Si buscas un METODO y no un tipo, usa consultar_firma_metodo_com.py")


if __name__ == "__main__":
    main()
