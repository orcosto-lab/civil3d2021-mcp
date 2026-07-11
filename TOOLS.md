# Índice de herramientas

Listado de módulos y herramientas del servidor, con su firma y comportamiento.
Todas las herramientas COM siguen el patrón `async def` + `_run()` interno +
`run_com(_run)`; los errores devuelven `{"error": "..."}` en vez de lanzar
excepciones.

## `scripts\`

| Archivo | Descripción |
|---|---|
| `activar_drawing2.scr` | Script SCR para activar un segundo documento abierto |
| `load_sacred_plugin.scr` | Script SCR para cargar el plugin Sacred |

## `scripts\templates\`

Plantillas Python listas para ejecutar contra Civil 3D via COM (pywin32),
sin pasar por el servidor MCP. Todas usan `GetActiveObject` (nunca `Dispatch`)
y `try/except`.

| Archivo | Operación |
|---|---|
| `borrar_objeto_por_handle.py` | Borra un objeto del ModelSpace por su handle hex |
| `crear_circulo.py` | Crea un círculo en el ModelSpace en capa y posición indicadas |
| `cambiar_capa_objetos_por_handle.py` | Cambia la capa de uno o varios objetos por handle |
| `copiar_objeto_con_desplazamiento.py` | Copia un objeto y lo desplaza con vector dx/dy/dz |
| `crear_puntos_cogo_desde_lista.py` | Crea puntos COGO desde lista; usa `GetInterfaceObject` + VARIANT `[Este, Norte, Elev]` |
| `borrar_puntos_cogo_por_numero.py` | Borra puntos COGO por número de punto |
| `editar_vertices_polilinea.py` | Reemplaza vértices de polilínea 2D o 3D por handle |
| `analisis_conectividad_extremos.py` | Detecta extremos libres y pares conectados entre polilíneas |
| `acotar_bloque_seccion.py` | Acota con MLeaders de nivel (Z real) un bloque de sección generado; interseca el plano de corte con las aristas 3D del modelo y calibra el bloque 2D. Incluye el LISP para volcar `Section.Vertices` (ilegible via COM externo) |

## `src\civil3d_mcp\`

| Archivo | Descripción |
|---|---|
| `__init__.py` | Marcador de paquete Python |
| `server.py` | Punto de entrada del servidor MCP; registra todos los módulos de herramientas |
| `client.py` | Cliente COM lazy para AutoCAD/Civil 3D (pywin32); gestiona `_acad` y `_doc` |
| `tools_drawing.py` | `info_dibujo`, `listar_capas`, `contar_objetos`, `listar_objetos` |
| `tools_cogo.py` | `listar_puntos_cogo`, `crear_punto_cogo` |
| `tools_lines.py` | `crear_linea`, `crear_polilinea` |
| `tools_surfaces.py` | `list_surfaces`, `elevacion_en_punto` |
| `tools_alignments.py` | `list_alignments`, `coordenadas_en_pk` |
| `tools_corridors.py` | `list_corridors` |
| `tools_layers.py` | `crear_capa`, `activar_capa`, `congelar_capa`, `bloquear_capa`, `eliminar_capa`, `eliminar_capas_vacias`, `cambiar_color_capa` |
| `tools_blocks.py` | `listar_bloques`, `insertar_bloque` |
| `tools_view.py` | `zoom_extension`, `zoom_todo`, `zoom_escala`, `zoom_previo`, `vista_planta`, `vista_isometrica_sw`, `regenerar_vista` |
| `tools_create.py` | `crear_texto`, `mover_a_capa`, `copiar_objeto`, `cambiar_capa_objetos`, `borrar_objeto`, `crear_circulo` |
| `tools_files.py` | `guardar_dibujo`, `guardar_como`, `purgar_dibujo` |
| `tools_script.py` | `ejecutar_script`, `listar_scripts`, `cargar_plugin_dll` |
| `tools_mesh.py` | `crear_malla_desde_triangulacion` — lee líneas/polilíneas 3D de una capa, detecta triángulos por adyacencia de aristas y crea `AcDbFace` (3DFace) via `_3DFACE` + `SendCommand`. Requiere `_UCS _W` previo para coordenadas UTM absolutas. Pensada para triangulación clásica (contorno + diagonales). `crear_malla_desde_polilineas` — cada polilínea de la capa se convierte directamente en una o varias 3DFace (sin detectar adyacencias entre polilíneas distintas); fan triangulation si tiene más de 4 vértices únicos. Pensada para capas con varios contornos/caras ya definidos (p.ej. peldaños de escalera). |
| `tools_cotas.py` | Dos herramientas: (1) `acotar_seccion(handle_seccion, handle_bloque, capas_modelo, ...)`: acota con MLeaders de nivel (Z real) un bloque de sección generado desde un `AcDbSection`, intersectando el plano con líneas/polilíneas 3D del modelo (wireframe), con calibración de casado del eje X (incl. vistas especulares XScale=-1); aborta si casan <80%. No soporta mallas/superficies (`AcDbSurface`). (2) `acotar_solidos_seccion(handle_bloque, vertices_seccion, capa_solidos, elevacion, ...)`: acota top/bottom de `AcDb3dSolid` (vigas, etc.) usando `Acad3DSolid.SectionSolid` + bounding box de la región resultante — sin calibración de casado, posición exacta por distancia real a lo largo de `vertices_seccion` (obligatorios aquí). Descarta sólidos con distancia fuera de `[0, longitud]` porque `SectionSolid` usa un plano infinito y puede capturar sólidos de un tramo vecino con igual orientación. **Limitación conocida:** cuando el bloque de sección contiene `AcDbSpline` (curvas, remates, bóvedas) además de `AcDbLine`, ninguna de las dos herramientas las detecta — hay que reconstruir el perfil aparte (ver `LECCIONES_TECNICAS.md`). |
| `tools_cache.py` | `escanear_capa_a_db(capa, incluir_vertices=True)`: vuelca todos los objetos de una capa (sin el límite de 100 de `listar_objetos`) a una BD SQLite local (`<carpeta_temporal>\<nombre_dwg>.sqlite`). Tablas: `entidades`(handle, tipo, capa, color, texto, punto_insercion, vertices JSON, num_vertices, escaneado_en) y `escaneos`(capa, timestamp, total). Cada escaneo reemplaza filas previas de esa capa. `consultar_db(sql)`: solo SELECT/WITH, conexión mode=ro, máximo 500 filas. Pensada para capas >100 objetos; para vistazos rápidos usar `listar_objetos`. |
| `tools_textos.py` | `buscar_textos(patron, capa="", regex=False)`: busca entidades con TextString (Text, MText, Attribute, MLeader...) por subcadena (case-insensitive) o regex; usa la cache SQLite si la capa está escaneada, si no escanea ModelSpace via COM; máximo 200 resultados. `seleccionar_objetos(handles, activar=True)`: establece la selección activa de Civil 3D (grips azules) via `sssetfirst` LISP + `SendCommand`; temporal (se pierde al hacer clic); `activar=False` limpia la selección. `seleccionar_por_filtro(capa="", tipo="", color=0)`: selecciona visualmente todos los objetos de ModelSpace que cumplan los filtros (AND); al menos uno obligatorio. Nota: `Highlight` COM no produce efecto visual desde proceso externo en Civil 3D 2021 — `sssetfirst` es la única vía fiable. |
| `tools_geometria.py` | `obtener_bounding_box(handle)`: bbox real WCS de cualquier entidad via `GetBoundingBox` COM (aviso: no usar en bloques rotados, sobre-estima el área). `encajar_bloque_en_superficie(handle_bloque, nombre_superficie, holgura)`: eleva un `AcDbBlockReference` en Z hasta enrasar por debajo de una superficie TIN en el punto más desfavorable; calcula la huella real rotada (bbox local de la definición + escala XY + rotación Z + traslación por `InsertionPoint`), no el bbox alineado a ejes — evita el error de sobre-estimar el área en bloques rotados. Asume rotación solo en Z. |
