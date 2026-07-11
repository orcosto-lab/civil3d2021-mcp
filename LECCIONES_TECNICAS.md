# Lecciones técnicas — API COM/ActiveX de Civil 3D

Lecciones acumuladas desarrollando este servidor, organizadas por categoría.
Se han eliminado referencias a proyectos, clientes, nombres de archivo y
rutas concretas — el contenido técnico se mantiene íntegro.

## 1. Conexión COM con Civil 3D

- Usar siempre `win32com.client.GetActiveObject("AutoCAD.Application")`,
  nunca `Dispatch()`, en scripts externos — `Dispatch` puede crear una
  instancia de AutoCAD nueva sin documento activo, causando
  `AttributeError: <unknown>.Points` aunque el código parezca correcto.
- Para acceder a Civil 3D (Points, objetos COGO) usar
  `acad.GetInterfaceObject("AeccXUiLand.AeccApplication.13.3")`. El mismo
  progid falla con `win32com.client.Dispatch()` directo.
- COM puede devolver `(-2147418111, 'La llamada fue rechazada por el
  destinatario.')` si Civil 3D tiene un comando pendiente o un diálogo
  abierto; cerrar/ESC en Civil 3D antes de reintentar.
- Un comando interactivo bloqueante en Civil 3D (p.ej. modo orbit activo)
  deja `ActiveDocument` en estado no accesible via COM, devolviendo errores
  como `<unknown>.Layers` o campos `None` silenciosos en vez de un error
  claro. Liberar el comando bloqueante antes de diagnosticar como fallo de
  código.
- Tras un comando que falla o deja un selection set "designado" pendiente
  en la línea de comandos, el COM de Civil 3D queda bloqueado
  (`<unknown>.ModelSpace`) hasta pulsar Esc manualmente en Civil 3D.
- Algunas herramientas (p.ej. info del dibujo) capturan excepciones por
  atributo individual y devuelven `None` en vez de propagar el error — si
  todo da `None`, probar con otra herramienta que no capture el error por
  campo, para ver el mensaje COM real.
- Renombrar la clave del servidor en la config de Claude Desktop fuerza una
  recarga limpia.
- La colección de puntos COGO a veces falla via COM; fallback: escanear
  ModelSpace directamente.

## 2. Puntos COGO

- La colección de puntos COGO (via `AeccXUiLand.AeccApplication`) se llama
  `Points`, no `CogoPoints` — un error fácil de cometer que hace fallar la
  creación de puntos silenciosamente mientras el listado (via fallback de
  escaneo de ModelSpace) sigue funcionando.
- `Points.Add()` requiere un VARIANT en orden **[Este, Norte, Elevación]**:
  `wc.VARIANT(pc.VT_ARRAY | pc.VT_R8, [este, norte, elev])`, como único
  argumento (sin booleano adicional). Invertir X/Y crea puntos en posición
  incorrecta sin dar error — `pt.Easting`/`pt.Northing` reflejan el orden
  pasado, no detectan el error automáticamente.
- La descripción del punto se asigna después via `pt.RawDescription`, no
  como argumento de `Add`.
- Caso validado: creación de ~30 puntos COGO de definición a partir de los
  vértices únicos de un conjunto de líneas en una capa de referencia,
  confirmado correcto tras corregir el progid y el orden del VARIANT.

## 3. SendCommand, idioma y scripts .scr

- Los comandos AutoCAD en inglés enviados via `SendCommand` o scripts
  `.scr` deben ir precedidos de `_` para funcionar en instalaciones en
  español (ej. `_3DFACE`, `_CLAYER`, `_LINE`, `_SCRIPT`). Sin el prefijo,
  Civil 3D en español devuelve "Comando desconocido" aunque el comando
  exista. El prefijo fuerza el nombre en inglés independientemente del
  idioma de la instalación — es el método estándar de Autodesk para
  scripts portables.
- `PFACE` no está disponible en Civil 3D 2021. Usar `_3DFACE` para caras
  triangulares (4 puntos, repitiendo el 3º como 4º).
- `SendCommand` directo (no desde `.scr`) tiene comportamiento distinto a
  un script `.scr`: un comando que funciona sin prefijo `_` en directo
  puede no funcionar igual desde script — para máxima portabilidad, añadir
  siempre `_`.
- En scripts `.scr`, `-LAYER` tampoco funciona en español; usar `_-LAYER`
  o gestionar capas via COM antes de lanzar el script.
- El comando Civil 3D en español para el sistema de coordenadas es `SCP`
  (no `UCS`).
- `SendCommand` es asíncrono — no sirve para secuencias que dependen de un
  resultado entre documentos.
- Patrón defensivo: enviar `doc.SendCommand("\x1b\x1b")` antes de cualquier
  `SendCommand` crítico cancela comandos pendientes o bloqueantes de
  operaciones anteriores.

## 4. Sistema de coordenadas (SCP/UCS)

- Antes de crear geometría con coordenadas absolutas (UTM) via
  `SendCommand`, resetear siempre el SCP a mundo con `_UCS\n_W\n`. Si el
  SCP está desplazado, los objetos se crean en coordenadas locales y
  aparecen en posición incorrecta sin dar error.
- `Add3DPoly` COM puro no depende del UCS:
  `ModelSpace.Add3DPoly(VARIANT(VT_ARRAY|VT_R8, [x,y,z,...]))`, sin
  `SendCommand` ni UCS. Deduplicar vértices consecutivos idénticos antes de
  la llamada.

## 5. Selección visual y selection sets

- `Highlight` COM no produce efecto visual desde un proceso externo en
  Civil 3D 2021 (ni con `obj.Update()` ni con `Regen` posterior) —
  `sssetfirst` via `SendCommand` es la única vía fiable para selección
  visual (grips azules).
- Patrón de construcción del selection set, de dentro a fuera:
  `lisp = "(ssadd)"; for h in reversed(handles): lisp = f'(ssadd (handent "{h}") {lisp})'`,
  después `doc.SendCommand(f"(sssetfirst nil {lisp}) ")`. Limpiar con
  `(sssetfirst nil nil)`.
- El pickfirst (`PickfirstSelectionSet`) es read-only via COM — no se
  puede escribir desde proceso externo; de ahí la necesidad de LISP
  in-process.
- Selection set por handle para comandos (sin selección visual):
  `(setq ss (ssadd))(ssadd (handent "H1") ss)...(command "_.CONVTOSURFACE" ss "")`
  — evita selección visual y pickfirst, fiable via `SendCommand`.
- La selección activa establecida con `sssetfirst` se pierde si el usuario
  hace clic en el dibujo. No modifica capas ni colores.
- Límite práctico: la cadena LISP de `sssetfirst` puede volverse muy larga
  con cientos de handles; si aparece un límite de longitud, resolver con
  un selection set nombrado intermedio.

## 6. Bounding box y bloques

- `obj.GetBoundingBox()` en un `AcDbBlockReference` **rotado en planta**
  devuelve el bbox alineado a ejes WCS, no las esquinas reales del bloque
  — sobre-estima el área en bloques rotados. Para la huella real: usar el
  bbox local de la definición del bloque (iterando sus entidades) +
  aplicar escala XY + rotación Z (`obj.Rotation`, radianes) + traslación
  por `obj.InsertionPoint`. Usar `EffectiveName` (no `Name`) por bloques
  dinámicos con nombre anónimo interno.
- Caso validado: una primera versión que muestreaba el bounding box
  alineado a ejes dio resultados incorrectos en un bloque rotado ~28° en
  planta; la versión con huella real rotada coincidió con el cálculo
  manual de control (diferencia final de pocos milímetros, atribuible a
  la holgura aplicada).

## 7. Secciones transversales (AcDbSection, bloques generados, MLeaders)

**Geometría de los bloques generados desde un plano de sección:**
- Un bloque generado desde un `AcDbSection` está a escala 1:1 y su Y local
  es la altura sobre la `Elevation` del plano: **cota_real = Y_local +
  Elevation**. Verificado al milímetro cruzando las Y locales de varios
  bloques con las Z reales de la intersección plano-modelo en distintos
  casos (decenas de puntos coincidentes cada vez, todos con desviación
  <2 cm).
- Con inserción sin rotación: `cota = Y_mundo - Y_insercion + Elevation`.
- Las vistas especulares se insertan con `XScaleFactor = -1`
  (`local_x = offset - distancia`).
- Los puntos que interesa acotar son las intersecciones del plano vertical
  de corte con las aristas 3D del modelo (líneas + polilíneas 3D).

**Lectura de vértices del AcDbSection:**
- `Section.Vertices` NO es legible via COM externo: lanza "Violación de
  bloqueo" (`eLockViolation`). Sí son legibles `Elevation`, `TopHeight`,
  `BottomHeight`, `State`. Workaround: LISP in-process via `SendCommand`
  que vuelca los vértices a fichero con
  `(vla-get-Vertices (vlax-ename->vla-object (handent "H")))`, formateando
  con `rtos` (`vl-princ-to-string` trunca a notación científica).
- `(load "...")` via `SendCommand` dispara el diálogo de seguridad
  SECURELOAD si la ruta no es de confianza — bloquea el COM hasta que el
  usuario acepta. Alternativas: aceptar manualmente, añadir la ruta a
  `TRUSTEDPATHS`, o evitar LISP deduciendo la línea de corte del bounding
  box de la sección (probando ambas diagonales y validando contra el
  bloque). El diálogo reaparece cada vez que cambia la ruta/contenido del
  script (cada edición cuenta como archivo "nuevo" para la verificación de
  firma). Ver sección 12 para la resolución vía control remoto de UI.

**MLeaders:**
- `ModelSpace.AddMLeader(pts, 0)` en pywin32 devuelve una **tupla**
  `(objeto, índice)` por el out-param `leaderLineIndex` — usar `ret[0]`.
  Ojo: la entidad se crea aunque el código posterior falle.
- El primer vértice del array es la punta de flecha. Asignar
  `ContentType = 2` (`acMTextContent`) antes de `TextString`.

**Emparejamiento sección-bloque:**
- El casado por Z únicamente (sin verificar posición X) da falsos
  positivos altos cuando el bloque tiene mucha geometría densa
  (rayado/texturas): un bloque con cientos de vértices locales puede casar
  con un plano equivocado solo por azar de tolerancia. La calibración
  fuerte (dirección + offset consistente para TODOS los puntos
  simultáneamente, no punto a punto) es el único test fiable para
  desambiguar — un casado del 89% con dirección/offset limpios es más
  fiable que un 64% con Z-only.
- Un layer de sección con dos bloques para la misma letra puede significar
  dos segmentos de corte consecutivos (una línea partida en 2 tramos que
  comparten vértice), no dos secciones distintas — reconocible por
  bounding boxes en planta contiguos en X.
- Un bloque con coordenadas Y locales ya en rango de cota real (en vez de
  0-8) delata una sección con `Elevation=0` en vez de la esperada —
  confirmar por casado exacto (offset=0.000).

**Reconstrucción de perfil directamente desde el bloque (sin modelo 3D):**
Cuando el corte pasa por geometría que las capas de wireframe no
representan bien, es posible reconstruir el perfil del bloque generado
solo con sus propias líneas: encadenar por vértices compartidos (grafo de
adyacencia con tolerancia ~0.01 m), separar componentes conexas, tomar la
componente principal (más nodos) como contorno real, filtrar antes por
longitud de línea (>0.3 m) para excluir rayado/textura.
`cota = Y_local_del_vertice + Elevation` del plano de sección.

**Splines en bloques de sección:**
- Los bloques de sección pueden contener `AcDbSpline` además de
  `AcDbLine`. La reconstrucción de perfil por grafo de adyacencia que solo
  mira `AcDbLine` deja cualquier tramo dibujado como spline completamente
  invisible, sin error ni aviso. Detección: el bbox completo del bloque no
  coincide con el bbox del grafo de líneas.
- Rasgo pequeño y aislado: extraer los puntos de control reales con
  `Spline.NumberOfControlPoints` + `Spline.GetControlPoint(i)`,
  identificar los vértices únicos (las splines suelen venir duplicadas en
  sentido inverso en exportaciones de Civil 3D).
- Curva larga casi continua (decenas de splines formando un perfil
  curvo): construir un grafo de adyacencia usando el primer y último punto
  de control de cada spline como nodo. A diferencia de las líneas, este
  grafo no tiene nodos de grado 1 (las splines vienen duplicadas en ambos
  sentidos, formando ciclos de grado 2) — la noción útil de "extremo" aquí
  es el diámetro del conjunto de puntos por componente conexa (los 2
  puntos más alejados entre sí), no el grado del nodo.
- Antes de dibujar cualquier extremo nuevo, comprobar contra los puntos ya
  acotados por el método de líneas — las curvas suelen empalmar justo en
  un vértice que la fase de líneas ya cotizó.

**Punto más alto/más bajo de una sección (lección anti-sobre-ingeniería):**
Cuando la `Elevation` de calibración ya es conocida y fiable, casi
cualquier pregunta sobre "el punto más alto/más bajo/más a la izquierda"
se responde con un max/min sobre los vértices ya presentes en el bloque
generado (`cota_pico = Y_max_local + Elevation`), sin tocar el modelo 3D
en absoluto. Reservar la intersección con modelo/superficies para cuando
realmente se necesite un dato que el bloque 2D no contenga.

**Cotas de sólidos 3D en un corte (`Acad3DSolid.SectionSolid`):**
- `SectionSolid(P1,P2,P3)` (3 puntos definen un plano) devuelve una
  `Region` con la sección real del sólido cortado. Tras usarla, hacer
  `region.Delete()` (es un objeto nuevo en el dibujo). Alternativas:
  `Acad3DSolid.IntersectWith` (puntos de intersección) y `SliceSolid`
  (corta y devuelve un sólido resultante).
- El plano de `SectionSolid` es **infinito**. Si dos tramos de sección
  consecutivos tienen distinta orientación pero los sólidos reales (p.ej.
  una fila de vigas) siguen casi rectos a través del vértice de unión, el
  plano de un tramo puede cortar sólidos que pertenecen al tramo vecino.
  Solución: descartar todo sólido cuya distancia proyectada a lo largo de
  la línea de corte caiga fuera de `[0, longitud_del_tramo]` (con
  tolerancia ~0.05 m).
- Con `SectionSolid`, la posición local de cada sólido es su distancia
  real proyectada sobre la línea de corte — no hace falta calibrar contra
  el bloque, porque el dato viene del sólido real, no de una aproximación
  por wireframe.

## 8. Superficies TIN, Surface y sólidos 3D

**Proceso: convertir superficie TIN (Civil 3D) a Surface nativa de AutoCAD**
Flujo confirmado y repetido con éxito en más de un caso real:

1. Localizar la superficie TIN (nombre, tipo `AeccDbSurfaceTin`, handle).
2. Extraer la triangulación como objetos AutoCAD — **no es automatizable
   via SendCommand**: `CONVTOSURFACE` directamente sobre el handle de la
   TIN falla ("objetos no se pueden convertir", `TinSurface` es un tipo de
   dato distinto). El comando correcto es `_AeccSurfaceExtractObjects`,
   pero es interactivo: pide seleccionar la superficie con click (no
   acepta selection set por handle via LISP/pickfirst) y abre un diálogo
   gráfico con checkboxes (Triángulos/Cara 3D, Contornos, Puntos,
   Límites...). No hay forma fiable de automatizarlo por script — requiere
   que el usuario lo ejecute manualmente y avise cuando termine. Resultado:
   N objetos `AcDbFace` nuevos en el dibujo.
3. Convertir las caras 3D a Surface: selection set por handle via AutoLISP
   + `_.CONVTOSURFACE` (mismo patrón que las mallas). Confirmado sin
   fallos sobre decenas de caras en una sola pasada.
4. Unir todas las superficies resultantes en una sola: mismo patrón de
   selección por handle con `_.UNION`.
5. Tras cada paso, si la llamada devuelve `<unknown>.ModelSpace`, el
   selection set "designado" quedó pendiente — pulsar Esc en Civil 3D y
   reintentar la lectura.

**Limitación conocida:** no existe vía COM/SendCommand para automatizar el
paso de extracción desde `TinSurface`. Si se repite a menudo, valorar la
API .NET de Civil 3D (`TinSurface.GetTriangles()`, namespace
`Autodesk.Civil.DatabaseServices`) para un plugin que lo haga sin
intervención manual — la API COM/ActiveX no expone esa colección de
triángulos directamente.

Caso validado: dos superficies reales convertidas con éxito (66 caras → 1
surface, y 26 caras → 1 surface).

**Comandos de solidificación:**
- `SURFTHICKEN` no existe en AutoCAD/Civil 3D 2021. Para un sólido con
  espesor real, probar `THICKEN` o `PRESSPULL`/`EXTRUDE` sobre la
  superficie.
- `_.UNION` sí funciona sobre `Surface` en AutoCAD 2021.

**Limitaciones de superficies en 2021 (via COM):**
- `AcadSurface.IntersectWith` (heredado por `AcDbLoftedSurface`) no está
  implementado en AutoCAD 2021 — error COM "Aún no se ha implementado" en
  ambas direcciones.
- `vla-Thicken` + `SectionSolid` sobre copia de `AcDbLoftedSurface`
  provocó un fallo no capturable por `vl-catch-all-apply`.
- Crear superficies desde puntos COGO o perfiles rasante no es
  implementable desde COM externo en Civil 3D 2021.

## 9. Perfiles dibujados ("guitarras") → polilíneas 3D

**Método validado (perfil dibujado → polilínea 3D):**
1. Localizar la polilínea del perfil (la de más vértices; suele ser
   `AcDb2dPolyline`) y calibrar con los textos de la guitarra, no con la
   escala gráfica: bandas de cotas de terreno + distancias a origen. El
   offset vertical (`Y_perfil - cota`) debe salir constante en todas las
   estaciones. El offset horizontal (`PK = X_perfil - X0`) debe dar escala
   1:1 verificable con la distancia a origen final.
2. Z de cada vértice del perfil = `Y - offset`; posición = distancia sobre
   la planta via mapeo por tramos anclado en los pozos/hitos reales
   (no en nodos intermedios del perfil).
3. `Add3DPoly` COM puro:
   `VARIANT(VT_ARRAY|VT_R8, [x,y,z,...] plano)`, sin `SendCommand` ni UCS.
   Deduplicar vértices consecutivos idénticos del perfil antes.

**Lecciones clave:**
- No anclar en nodos intermedios de la guitarra: si la posición del nodo
  en el perfil no coincide exactamente con el vértice de planta, el
  anclaje intermedio estira/comprime los subtramos y produce desviaciones
  de hasta varios centímetros al superponer perfiles. Anclar solo en
  puntos de control fiables (pozos, hitos) y repartir la diferencia
  uniformemente dentro del tramo entre ellos.
- Los textos de la guitarra pueden tener erratas puntuales (cota
  duplicada de la estación anterior); en caso de conflicto, la geometría
  de la polilínea del perfil manda sobre el texto rotulado si el resto de
  estaciones son consistentes con ella.
- Los rótulos de la guitarra pueden tener un offset X constante respecto a
  la estación real — usar la polilínea del perfil como referencia de X0,
  no los textos.
- Las capas de planta pueden contener residuos (tramos sueltos muy
  cortos): identificar el recorrido real comparando longitud en planta vs
  span X del perfil.

## 10. Encoding y entorno Python

- Python 3.14 es incompatible con `asyncio` en este contexto; usar Python
  3.11.
- Guardar los `.py` como ANSI o con `PYTHONUTF8=1` para evitar errores
  `cp1252`.
- `pip install -e .` debe ejecutarse desde la carpeta del proyecto, no
  desde `System32`.
- Tras cualquier edición de un módulo: borrar `__pycache__` y reiniciar
  Claude Desktop antes de probar.

## 11. Extracción de datos en capas grandes

- `listar_objetos` corta en 100 objetos y no devuelve `TextString` ni
  vértices completos: para capas grandes, la vía es un escaneo COM a una
  BD SQLite local (ver `tools_cache.py` en `TOOLS.md`) con tablas
  `entidades` y `escaneos`. `consultar_db` es solo SELECT, conexión
  read-only, máximo 500 filas. Para vistazos rápidos de <100 objetos sigue
  siendo preferible `listar_objetos` (sin coste de escaneo). La cache
  caduca si el dibujo se edita en paralelo — re-escanear al inicio de cada
  pasada de análisis.
- Multi-line Python en un REPL interactivo: envolver en `exec('''...''')`
  para evitar errores de indentación. `python -c` multilínea falla de
  forma fiable — escribir siempre el script a fichero y ejecutarlo.

## 12. Diálogos bloqueantes de seguridad (SECURELOAD)

Flujo validado para resolver el diálogo SECURELOAD ("Seguridad - Archivo
ejecutable no firmado") de forma autónoma, via control remoto de UI:

1. Confirmar que la ventana activa es Civil 3D antes de capturar pantalla
   (si no lo es, la captura solo verá la app de control tapando Civil 3D).
2. Capturar pantalla (base64) y decodificarla a imagen para poder verla.
3. Localizar el botón en la imagen, convertir coordenadas de la imagen
   (posiblemente redimensionada) a coordenadas reales de pantalla con el
   factor de escala de la resolución real.
4. Clic sobre el botón real en pantalla.
5. Captura de verificación tras el clic para confirmar que el diálogo se
   cerró antes de continuar con el flujo COM.

Elegir siempre **"Cargar una vez"** en vez de "Cargar siempre": este
último modificaría la configuración de confianza de Civil 3D de forma
permanente, lo cual es una modificación de seguridad que no debe hacerse
sin pedirlo explícitamente.

**Lección asociada:** cuando un script que espera un fichero de resultado
(`SendCommand` + bucle de sondeo) hace timeout porque el diálogo
SECURELOAD aún no se ha aceptado, el proceso ya agotó su bucle de espera
para cuando el diálogo se cierra después — el fichero nunca se crea con
esa ejecución. Hay que **relanzar el script después** de cerrar el
diálogo, no asumir que se resuelve solo tras aceptar.
