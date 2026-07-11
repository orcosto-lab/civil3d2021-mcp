# civil3d2021-mcp

[English](#english) | [Español](#español)

---

## English

MCP (Model Context Protocol) server that connects an LLM assistant (Claude)
to Autodesk Civil 3D via COM (`pywin32`). It lets you operate Civil 3D —
surfaces, alignments, COGO points, layers, profiles, cross-sections,
scripts — directly from a conversation with Claude, without going through
the GUI.

Tested on Civil 3D 2021; it should work on other versions that expose the
same AutoCAD/Civil 3D COM/ActiveX API.

### Requirements

- Windows with Autodesk Civil 3D installed and open
- Python 3.11 (not compatible with 3.14, due to `asyncio` issues)
- `pip install mcp fastmcp pywin32`

### Installation

```bash
git clone https://github.com/<your-username>/civil3d2021-mcp.git
cd civil3d2021-mcp
python -m pip install -e .
```

### Configuration in Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "civil3d-mcp": {
      "command": "python",
      "args": ["-m", "civil3d_mcp.server"],
      "env": {
        "PYTHONPATH": "PATH_TO_REPO\\src",
        "CIVIL3D_BIN_PATH": "C:\\Program Files\\Autodesk\\AutoCAD 2021\\C3D"
      }
    }
  }
}
```

### Architecture

Modular FastMCP server (`src/civil3d_mcp/`). Each `tools_*.py` is an
independent tool domain, registered in `server.py`:

- `tools_drawing.py` — drawing/project info
- `tools_cogo.py` — COGO points
- `tools_lines.py` — lines and polylines
- `tools_surfaces.py` — TIN surfaces
- `tools_alignments.py` — alignments
- `tools_corridors.py` — corridors
- `tools_layers.py` — layers
- `tools_blocks.py` — blocks
- `tools_view.py` — view and zoom
- `tools_create.py` — object creation
- `tools_files.py` — file management
- `tools_script.py` — script execution and .NET plugin loading
- `tools_mesh.py` — 3D meshes (3DFace) from triangulations or polylines
- `tools_geometria.py` — real bounding box and fitting blocks onto TIN surfaces
- `tools_cotas.py` — elevation labels (MLeader) on cross-section blocks
- `tools_cache.py` — SQLite entity cache for large layers
- `tools_textos.py` — text search and visual selection

`scripts/templates/` contains standalone Python scripts that replicate some
operations without going through the MCP server, useful as reference or for
quick one-off tests directly against Civil 3D.

### Additional documentation

- [`TOOLS.md`](TOOLS.md) — full tool index by module, with signature and behavior.
- [`LECCIONES_TECNICAS.md`](LECCIONES_TECNICAS.md) — lessons learned about the behavior of Civil 3D's COM/ActiveX API (in Spanish; useful for anyone extending the server).

### Credits

Developed by Pedro Orcos, with Claude (Anthropic) as co-author: design and
implementation of most of the tools, debugging of the COM API, and writing
of this repository's technical documentation.

#### Related projects

Inspired by the general idea behind [barbosaihan/civil3d-mcp](https://github.com/barbosaihan/civil3d-mcp)
(an MCP server for Civil 3D). This is not a fork: the architecture is
different — that project uses TypeScript plus a C#/Roslyn plugin that
executes code inside Civil 3D via NETLOAD/TCP, while this server is pure
Python over COM/ActiveX (`pywin32`) with fixed per-domain tools. No code is
shared between the two.

### License

No license defined yet — personal use. Get in touch before reusing this in
a commercial context.

---

## Español

Servidor MCP (Model Context Protocol) que conecta un asistente LLM (Claude) con
Autodesk Civil 3D via COM (`pywin32`). Permite operar Civil 3D — superficies,
alineaciones, puntos COGO, capas, perfiles, secciones, scripts — directamente
desde una conversación con Claude, sin pasar por la interfaz gráfica.

Probado sobre Civil 3D 2021, debería funcionar sobre otras versiones que
expongan la misma API COM/ActiveX de AutoCAD y Civil 3D.

### Requisitos

- Windows con Autodesk Civil 3D instalado y abierto
- Python 3.11 (no compatible con 3.14 por temas de `asyncio`)
- `pip install mcp fastmcp pywin32`

### Instalación

```bash
git clone https://github.com/<tu-usuario>/civil3d2021-mcp.git
cd civil3d2021-mcp
python -m pip install -e .
```

### Configuración en Claude Desktop

Añadir en `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "civil3d-mcp": {
      "command": "python",
      "args": ["-m", "civil3d_mcp.server"],
      "env": {
        "PYTHONPATH": "RUTA_AL_REPO\\src",
        "CIVIL3D_BIN_PATH": "C:\\Program Files\\Autodesk\\AutoCAD 2021\\C3D"
      }
    }
  }
}
```

### Arquitectura

Servidor FastMCP modular (`src/civil3d_mcp/`). Cada `tools_*.py` es un dominio
de herramientas independiente, registrado en `server.py`:

- `tools_drawing.py` — info del dibujo/proyecto
- `tools_cogo.py` — puntos COGO
- `tools_lines.py` — líneas y polilíneas
- `tools_surfaces.py` — superficies TIN
- `tools_alignments.py` — alineaciones
- `tools_corridors.py` — corredores
- `tools_layers.py` — capas
- `tools_blocks.py` — bloques
- `tools_view.py` — vista y zoom
- `tools_create.py` — creación de objetos
- `tools_files.py` — gestión de archivos
- `tools_script.py` — ejecución de scripts y carga de plugins .NET
- `tools_mesh.py` — mallas 3D (3DFace) desde triangulaciones o polilíneas
- `tools_geometria.py` — bounding box real y encaje de bloques sobre superficies TIN
- `tools_cotas.py` — cotas de nivel (MLeader) sobre bloques de sección
- `tools_cache.py` — cache SQLite de entidades para capas grandes
- `tools_textos.py` — búsqueda de textos y selección visual

`scripts/templates/` contiene scripts Python standalone que replican algunas
operaciones sin pasar por el servidor MCP, útiles como referencia o para
pruebas puntuales directas contra Civil 3D.

### Documentación adicional

- [`TOOLS.md`](TOOLS.md) — índice completo de herramientas por módulo, con firma y comportamiento.
- [`LECCIONES_TECNICAS.md`](LECCIONES_TECNICAS.md) — lecciones acumuladas sobre el comportamiento de la API COM/ActiveX de Civil 3D (útil para quien quiera extender el servidor).

### Créditos

Desarrollado por Pedro Orcos, con Claude (Anthropic) como coautor: diseño e
implementación de la mayoría de las herramientas, depuración de la API COM y
redacción de la documentación técnica de este repositorio.

#### Proyectos relacionados

Inspirado en la idea general de [barbosaihan/civil3d-mcp](https://github.com/barbosaihan/civil3d-mcp)
(servidor MCP para Civil 3D). No es un fork: la arquitectura es distinta —
aquel usa TypeScript + un plugin C#/Roslyn que ejecuta código dentro de
Civil 3D via NETLOAD/TCP, mientras que este servidor es Python puro sobre
COM/ActiveX (`pywin32`) con herramientas fijas por dominio. No se comparte
código entre ambos.

### Licencia

Sin licencia definida todavía — uso personal. Contactar antes de reutilizar
en un contexto comercial.
