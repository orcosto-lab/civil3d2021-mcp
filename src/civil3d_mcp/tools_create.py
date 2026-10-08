"""
tools_create.py  -  Creacion de entidades y manipulacion de objetos
"""
from __future__ import annotations
import logging
import time
from typing import Any, Callable
import win32com.client
import pythoncom
from mcp.server.fastmcp import FastMCP
from .client import Civil3DClient, con_reintentos, forzar_escape_civil3d

log = logging.getLogger("civil3d_mcp.tools.create")


def register(mcp: FastMCP, client: Civil3DClient, run_com: Callable) -> None:

    @mcp.tool(
        name="forzar_escape_civil3d",
        description=(
            "Pulsa Escape REAL a nivel de Windows sobre la ventana de Civil3D/"
            "AutoCAD -- para liberar un comando colgado enviado via SendCommand "
            "(p.ej. EXPLODE atascado en 'Designe objeto:'). LECCION: un ESC "
            "dentro de la propia cadena SendCommand NO funciona (SendCommand "
            "rechaza la llamada entera con 'Entrada no valida'); esta tool usa "
            "Application.HWND + SetForegroundWindow + keybd_event (win32api), "
            "no COM. SIEMPRE verifica que el foco realmente cambio antes de "
            "mandar la tecla -- si Windows bloquea el cambio de foco (puede "
            "pasar, ver LECCION del 'foreground lock' mas abajo), NO envia "
            "nada y lo reporta, en vez de arriesgarse a pulsar Escape en la "
            "ventana equivocada. LECCION (28/09/2026): un SetForegroundWindow "
            "\"a pelo\" desde un proceso en segundo plano (este servidor MCP) "
            "puede fallar con 'No error message is available' por el "
            "'foreground lock' de Windows -- confirmado en vivo, dejo un "
            "EXPLODE colgado sin liberar. Arreglado con AttachThreadInput "
            "(tecnica estandar Win32) antes de pedir el foco. Usar solo cuando se sospeche un "
            "comando colgado esperando seleccion/input -- no es un Escape de "
            "uso general para cancelar dialogos arbitrarios sin verificar antes "
            "con leer_historial_comandos/info_dibujo que hay algo realmente "
            "atascado. Reutilizable desde cualquier flujo que dependa de "
            "SendCommand, no exclusiva de explotar_objeto/explotar_por_handle."
        ),
    )
    async def forzar_escape_civil3d_tool() -> dict[str, Any]:
        try:
            def _run():
                return forzar_escape_civil3d(client)
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="borrar_objeto",
        description="Borra un objeto del dibujo identificado por su handle.",
    )
    async def borrar_objeto(
        handle: str,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                obj = doc.HandleToObject(handle)
                obj.Delete()
                return {"success": True, "handle": handle}
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="explotar_objeto",
        description=(
            "Explota un objeto (por handle) en sus entidades componentes, via el "
            "comando EXPLODE. LECCION: usa SendCommand/LISP, NUNCA el metodo COM "
            ".Explode() del objeto -- confirmado en vivo que ACAD_PROXY_ENTITY no "
            "expone .Explode() por automatizacion (falla con 'unknown.Explode'), "
            "solo el comando de linea (via graficos de proxy internos) logra "
            "descomponerlo. LECCION: SendCommand es asincrono (cola de teclado de "
            "AutoCAD); esta tool sondea cada 0.5s hasta timeout_seg comprobando si "
            "el handle original desaparecio (senal de explode completado) antes de "
            "responder -- un 'success: true' aqui SI confirma que el objeto ya no "
            "existe, a diferencia de otras tools SendCommand del catalogo. Si el "
            "handle sigue existiendo al agotar timeout_seg, se reporta success: "
            "false (objeto no explotable, o comando aun en cola: subir timeout_seg). "
            "No enumera las entidades nuevas resultantes: usa listar_objetos/"
            "escanear_capa_a_db sobre la capa despues de esta tool para verlas. "
            "Envuelve el explode en UNDO BEGIN/END (un solo Ctrl+Z lo deshace). "
            "LECCION (wiki civil3d-com-api.md #5): el selection set para el comando "
            "se construye SIEMPRE en dos pasos -- '(setq ss (ssadd)) (ssadd "
            "(handent h) ss)' -- nunca con la forma corta de un solo argumento "
            "'(ssadd (handent h))'; esta ultima dejo el EXPLODE colgado esperando "
            "'Designe objeto:' indefinidamente en pruebas reales (28/09/2026), "
            "incluso con SendCommand devolviendo control normalmente. "
            "LECCION (28/09/2026): el patron de dos pasos por si solo NO elimina "
            "el atasco -- es intermitente, mismo LISP a veces se cuelga y a veces "
            "no con el mismo tipo de objeto (AcDbZombieEntity/proxy). El objeto SI "
            "se explota igual aunque la linea de comandos quede colgada (verificado "
            "con Pedro mirando la pantalla), pero hace falta una pulsacion de "
            "teclado real (Pedro, o computer-use) para liberar la consola despues -- "
            "NO hay forma de autoliberarla desde el propio comando. PROBADO Y "
            "DESCARTADO (28/09/2026): anadir un caracter ESC real (chr(27)) al "
            "final de la cadena SendCommand, incluso pegado tras un comando ya "
            "completo (no como unico contenido) -- SendCommand rechaza la llamada "
            "entera con 'Entrada no valida' (COM exception sincrona) y el EXPLODE "
            "no llega a ejecutarse en absoluto. No usar ESC en ninguna forma "
            "dentro de una cadena SendCommand. LECCION (28/09/2026, integrado): "
            "tras el SendCommand, la tool espera 0.4s y llama SIEMPRE a "
            "forzar_escape_civil3d() (pulsacion real a nivel de Windows, ver esa "
            "tool) para liberar el atasco -- Pedro confirmo que el comando se "
            "queda colgado de forma sistematica, no solo a veces. El resultado "
            "de esa llamada viaja en el campo 'escape_aplicado' de la respuesta; "
            "revisarlo si 'success' sale false para saber si el fallo fue no "
            "conseguir el foco de la ventana (no se llego a pulsar nada) u otra "
            "causa. Pulsar Escape sobre una consola ya libre es inofensivo (no "
            "cancela nada), asi que no hace falta detectar el atasco antes de "
            "llamarlo."
        ),
    )
    async def explotar_objeto(handle: str, timeout_seg: float = 8.0) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                try:
                    doc.HandleToObject(handle)
                except Exception as exc:
                    return {"error": f"Handle '{handle}' no encontrado: {exc}"}

                cmd = (
                    f'(progn (command "_.undo" "_begin") '
                    f'(setq ss (ssadd)) (ssadd (handent "{handle}") ss) '
                    f'(command "_.explode" ss "") '
                    f'(command "_.undo" "_end") (princ)) '
                )
                doc.SendCommand(cmd)

                time.sleep(0.4)
                escape = forzar_escape_civil3d(client)

                explotado = False
                intentos = max(1, int(timeout_seg / 0.5))
                for _ in range(intentos):
                    time.sleep(0.5)
                    try:
                        doc.HandleToObject(handle)
                    except Exception:
                        explotado = True
                        break

                if not explotado:
                    return {
                        "success": False,
                        "handle": handle,
                        "escape_aplicado": escape,
                        "aviso": (
                            f"El objeto sigue existiendo tras {timeout_seg}s: no se "
                            "exploto (tipo no explotable) o el comando sigue en "
                            "cola. Verificar con leer_historial_comandos."
                        ),
                    }

                return {
                    "success": True,
                    "handle_original": handle,
                    "explotado": True,
                    "escape_aplicado": escape,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="explotar_por_handle",
        description=(
            "Explota una lista de objetos (por handle), uno detras de otro -- "
            "NO en un unico EXPLODE de lote. LECCION (28/09/2026, documentacion "
            "oficial Autodesk, comando EXPLODE): \"If you're using a script or "
            "an ObjectARX function, you can explode only one object at a time\" "
            "-- es una limitacion oficial y dura de AutoCAD, no un bug propio: "
            "un unico selection set con varios handles pasado a '_.explode' via "
            "SendCommand solo procesa UNO (confirmado en pruebas reales "
            "28/09/2026, mismo resultado con 0.4s y con 1.9s de espera previa -- "
            "no era un problema de timing). Por eso esta tool hace, por dentro, "
            "un EXPLODE independiente por cada handle (mismo patron que "
            "explotar_objeto: SendCommand + forzar_escape_civil3d + sondeo de "
            "existencia), en un bucle -- la llamada sigue siendo unica desde "
            "fuera, pero tarda aprox. N * (0.4s + sondeo) para N handles; sube "
            "timeout_seg (es POR HANDLE, no para el lote entero) si algun "
            "objeto tarda mas. Los que fallen se reportan en no_explotados sin "
            "abortar el resto. No enumera las entidades nuevas resultantes: usa "
            "escanear_capa_a_db/listar_objetos sobre la capa despues de esta "
            "tool. Cada EXPLODE individual va envuelto en su propio UNDO "
            "BEGIN/END (un Ctrl+Z deshace solo el ultimo objeto, no el lote "
            "completo -- a diferencia del diseño anterior de esta tool). "
            "PENDIENTE: no hay cifra calibrada para lotes grandes (decenas/"
            "cientos de handles) -- validar con pruebas reales antes de fiarse "
            "en produccion; el tiempo total y el riesgo de tocar limites de "
            "timeout del propio framework MCP crecen con el tamano del lote. "
            "LECCION (28/09/2026): un solo forzar_escape_civil3d() tras el "
            "SendCommand no siempre basta -- en pruebas reales con un lote "
            "grande, el segundo handle del bucle fallo porque la consola "
            "seguia colgada del primero. Ahora se llama a "
            "forzar_escape_civil3d() DOS veces por iteracion (tras el "
            "SendCommand y otra vez al cerrar, antes de pasar al siguiente "
            "handle), y el propio SendCommand va en try/except: si falla "
            "(consola aun ocupada), se marca ese handle como no explotado y se "
            "sigue con el resto en vez de abortar el lote entero. Con esto, "
            "para lotes grandes (>~50 handles) sigue sin ser un metodo rapido: "
            "Pedro senalo en pruebas reales que el coste por objeto hace que "
            "no compense frente a seleccionar todo y explotar una vez de forma "
            "interactiva en Civil3D para conversiones masivas -- esta tool "
            "esta pensada para lotes pequenos/moderados, no como sustituto de "
            "un EXPLODE manual masivo."
        ),
    )
    async def explotar_por_handle(
        handles: list[str],
        timeout_seg: float = 8.0,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc

                existentes = []
                no_encontrados = []
                for h in handles:
                    try:
                        doc.HandleToObject(h)
                        existentes.append(h)
                    except Exception:
                        no_encontrados.append(h)

                if not existentes:
                    return {
                        "success": False,
                        "error": "Ninguno de los handles indicados existe en el dibujo.",
                        "no_encontrados": no_encontrados,
                    }

                explotados = []
                no_explotados = []
                escapes_con_error = []

                for h in existentes:
                    cmd = (
                        f'(progn (command "_.undo" "_begin") '
                        f'(setq ss (ssadd)) (ssadd (handent "{h}") ss) '
                        f'(command "_.explode" ss "") '
                        f'(command "_.undo" "_end") (princ)) '
                    )
                    try:
                        doc.SendCommand(cmd)
                    except Exception as exc:
                        # La consola puede seguir colgada de un handle anterior
                        # si su escape de cierre no basto -- intentar liberarla
                        # antes de continuar con el siguiente, en vez de abortar
                        # todo el lote.
                        escapes_con_error.append({"handle": h, "error_sendcommand": str(exc)})
                        forzar_escape_civil3d(client)
                        no_explotados.append(h)
                        continue

                    time.sleep(0.4)
                    escape = forzar_escape_civil3d(client)
                    if not escape.get("success"):
                        escapes_con_error.append({"handle": h, "escape": escape})

                    ok = False
                    intentos = max(1, int(timeout_seg / 0.5))
                    for _ in range(intentos):
                        time.sleep(0.5)
                        try:
                            doc.HandleToObject(h)
                        except Exception:
                            ok = True
                            break

                    # Escape defensivo de cierre de iteracion: si el primero no
                    # basto (o el sondeo dejo la consola en un estado raro), no
                    # queremos arrastrar el atasco al SendCommand del siguiente
                    # handle del bucle -- pulsar Escape sobre una consola ya
                    # libre es inofensivo, asi que se hace siempre.
                    escape_cierre = forzar_escape_civil3d(client)
                    if not escape_cierre.get("success"):
                        escapes_con_error.append({"handle": h, "escape_cierre": escape_cierre})

                    if ok:
                        explotados.append(h)
                    else:
                        no_explotados.append(h)

                return {
                    "success": True,
                    "solicitados": len(handles),
                    "total_explotados": len(explotados),
                    "explotados": explotados,
                    "no_explotados": no_explotados,
                    "no_encontrados": no_encontrados,
                    "escapes_con_error": escapes_con_error,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_circulo",
        description="Crea un circulo en el plano XY centrado en (x, y, z) con el radio indicado.",
    )
    async def crear_circulo(
        x: float,
        y: float,
        z: float,
        radio: float,
        capa: str = "0",
    ) -> dict[str, Any]:
        try:
            def _run():
                ms = client.model_space
                centro = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z]
                )
                obj = ms.AddCircle(centro, radio)
                obj.Layer = capa
                return {
                    "success": True,
                    "handle": obj.Handle,
                    "centro": [x, y, z],
                    "radio": radio,
                    "capa": capa,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_punto",
        description=(
            "Crea un punto AutoCAD simple (AcDbPoint) en las coordenadas "
            "indicadas. LECCION (verificado en vivo 28/09/2026): la capa "
            "indicada en 'capa' debe existir ya en el dibujo -- si no existe, "
            "falla con 'Clave no encontrada' al asignar obj.Layer (no la crea "
            "sola). Crear la capa antes con crear_capa si hace falta."
        ),
    )
    async def crear_punto(
        x: float,
        y: float,
        z: float = 0.0,
        capa: str = "0",
    ) -> dict[str, Any]:
        try:
            def _run():
                ms = client.model_space
                pt = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z]
                )
                obj = ms.AddPoint(pt)
                obj.Layer = capa
                return {
                    "success": True,
                    "handle": obj.Handle,
                    "coordenadas": [x, y, z],
                    "capa": capa,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_puntos_multiples",
        description=(
            "Crea varios puntos AutoCAD simples (AcDbPoint) de una sola vez a partir "
            "de una lista de coordenadas [x, y, z]. AutoCAD no expone un metodo COM "
            "de creacion en lote para AcDbPoint (a diferencia de los puntos COGO de "
            "Civil 3D, que si tienen Points.AddMultiple): esta tool llama a AddPoint "
            "una vez por punto dentro de una sola invocacion, evitando N idas y "
            "vueltas MCP separadas. Un fallo en un punto no aborta el resto (se "
            "reporta en 'errores'), y cada AddPoint individual usa con_reintentos "
            "ante contencion COM transitoria (RPC_E_CALL_REJECTED) sin repetir "
            "puntos ya creados. LECCION (verificado en crear_punto 28/09/2026): "
            "la capa indicada debe existir ya en el dibujo -- crearla antes con "
            "crear_capa si hace falta, o cada punto fallara con 'Clave no "
            "encontrada' (se reportaria en 'errores', no abortaria el resto)."
        ),
    )
    async def crear_puntos_multiples(
        coordenadas: list[list[float]],
        capa: str = "0",
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        coordenadas : list[[x, y, z]]
            Lista de puntos a crear, cada uno como [x, y, z].
        capa : str
            Capa destino para todos los puntos creados (por defecto "0").
        """
        try:
            def _run():
                if not coordenadas:
                    return {"error": "coordenadas no puede estar vacio."}
                ms = client.model_space
                creados = []
                errores = []
                for i, c in enumerate(coordenadas):
                    if len(c) != 3:
                        errores.append({
                            "indice": i,
                            "error": f"cada punto debe tener 3 valores [x,y,z], recibido: {c}",
                        })
                        continue
                    try:
                        def _add_uno():
                            pt_var = win32com.client.VARIANT(
                                pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                [float(c[0]), float(c[1]), float(c[2])],
                            )
                            obj = ms.AddPoint(pt_var)
                            obj.Layer = capa
                            return obj.Handle
                        creados.append(con_reintentos(_add_uno))
                    except Exception as exc:
                        errores.append({"indice": i, "coordenadas": c, "error": str(exc)})
                return {
                    "success": True,
                    "solicitados": len(coordenadas),
                    "creados": len(creados),
                    "handles": creados,
                    "capa": capa,
                    "errores": errores,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="crear_texto",
        description="Inserta un texto de una linea en el dibujo en las coordenadas indicadas.",
    )
    async def crear_texto(
        texto: str,
        x: float,
        y: float,
        z: float = 0.0,
        altura: float = 1.0,
        capa: str = "0",
    ) -> dict[str, Any]:
        try:
            def _run():
                ms = client.model_space
                pt = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8,
                    [x, y, z],
                )
                obj = ms.AddText(texto, pt, altura)
                obj.Layer = capa
                return {
                    "success": True,
                    "handle": obj.Handle,
                    "texto": texto,
                    "capa": capa,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="mover_a_capa",
        description=(
            "Mueve todos los objetos de una capa origen a una capa destino. "
            "Crea la capa destino si no existe."
        ),
    )
    async def mover_a_capa(capa_origen: str, capa_destino: str) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                ms = doc.ModelSpace
                nombres = [c.Name.lower() for c in doc.Layers]
                if capa_destino.lower() not in nombres:
                    doc.Layers.Add(capa_destino)
                movidos = 0
                for obj in ms:
                    if obj.Layer.lower() == capa_origen.lower():
                        obj.Layer = capa_destino
                        movidos += 1
                return {
                    "success": True,
                    "origen": capa_origen,
                    "destino": capa_destino,
                    "objetos_movidos": movidos,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="cambiar_capa_objetos",
        description="Cambia la capa de uno o varios objetos identificados por sus handles.",
    )
    async def cambiar_capa_objetos(
        handles: list[str],
        capa_destino: str,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                # Crear capa destino si no existe
                nombres = [c.Name.lower() for c in doc.Layers]
                if capa_destino.lower() not in nombres:
                    doc.Layers.Add(capa_destino)
                movidos = []
                errores = []
                for handle in handles:
                    try:
                        obj = doc.HandleToObject(handle)
                        obj.Layer = capa_destino
                        movidos.append(handle)
                    except Exception as e:
                        errores.append({"handle": handle, "error": str(e)})
                return {
                    "success": True,
                    "movidos": movidos,
                    "capa_destino": capa_destino,
                    "errores": errores,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(
        name="copiar_objeto",
        description="Copia un objeto (por handle) desplazado por dx, dy, dz.",
    )
    async def copiar_objeto(
        handle: str,
        dx: float,
        dy: float,
        dz: float = 0.0,
    ) -> dict[str, Any]:
        try:
            def _run():
                doc = client.active_doc
                obj = doc.HandleToObject(handle)
                pt_base = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0, 0.0, 0.0]
                )
                pt_dest = win32com.client.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, [dx, dy, dz]
                )
                copia = obj.Copy()
                copia.Move(pt_base, pt_dest)
                return {
                    "success": True,
                    "handle_original": handle,
                    "handle_copia": copia.Handle,
                }
            return await run_com(_run)
        except Exception as exc:
            return {"error": str(exc)}
