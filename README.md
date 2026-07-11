# civil3d2021-mcp

Servidor MCP (Model Context Protocol) que conecta un asistente LLM (Claude) con
Autodesk Civil 3D via COM (`pywin32`). Permite operar Civil 3D — superficies,
alineaciones, puntos COGO, capas, perfiles, secciones, scripts — directamente
desde una conversación con Claude, sin pasar por la interfaz gráfica.

Probado sobre Civil 3D 2021, debería funcionar sobre otras versiones que
expongan la misma API COM/ActiveX de AutoCAD y Civil 3D.

## Requisitos

- Windows con Autodesk Civil 3D instalado y abierto
- Python 3.11 (no compatible con 3.14 por temas de `asyncio`)
- `pip install mcp fastmcp pywin32`

## Instalación

```bash
git clone https://github.com/<tu-usuario>/civil3d2021-mcp.git
cd civil3d2021-mcp
python -m pip install -e .
```

## Configuración en Claude Desktop

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

## Arquitectura

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

## Documentación adicional

- [`TOOLS.md`](TOOLS.md) — índice completo de herramientas por módulo, con firma y comportamiento.
- [`LECCIONES_TECNICAS.md`](LECCIONES_TECNICAS.md) — lecciones acumuladas sobre el comportamiento de la API COM/ActiveX de Civil 3D (útil para quien quiera extender el servidor).

## Créditos

Desarrollado por Pedro Orcos, con Claude (Anthropic) como coautor: diseño e
implementación de la mayoría de las herramientas, depuración de la API COM y
redacción de la documentación técnica de este repositorio.

## Licencia

Sin licencia definida todavía — uso personal. Contactar antes de reutilizar
en un contexto comercial.
