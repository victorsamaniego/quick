# QuickGo: tracking real y Web Push

## Base y alcance

Rama: `feat/live-delivery-tracking-webpush`, creada desde `origin/main` actualizado (`0ba6c9a`). Worktree independiente; se preservaron los cambios anteriores del directorio principal.

No push, merge, deploy, Railway, acceso a producción ni ejecución de migraciones. No se leyeron archivos de secretos. Las pruebas usan datos ficticios y bases SQLite aisladas.

## Causa del bug y piezas existentes

- `_order_destination.html` y `order_destination_map.js` mostraban el destino confirmado del comprador. No tenían marker ni listener del repartidor.
- `realtime.py` ya tenía Socket.IO, autorización de rooms, `order_rooms`, límites por cuenta y `delivery_location_update`. Este último solo emitía coordenadas, sin persistencia, timestamp ni condición de reparto activo.
- El dashboard del delivery consultaba GPS cada cinco segundos y actualizaba `User.latitude/longitude`, incluso sin pedido. Ese flujo no enviaba la posición del pedido al comprador/comercio.
- Las plantillas usaban `order.business`, pero faltaba la relación ORM. Se añadió la relación con `Business.orders` para obtener el punto fijo real de retiro.
- Existían QuickRealtime, audio local, notificaciones segmentadas e inbox durable. El service worker únicamente cacheaba assets públicos y se registraba en `/static/`; faltaban Push API, VAPID, suscripciones y listeners `push`/`notificationclick`.

## Arquitectura final

Una sola conexión Socket.IO y el dispatcher QuickRealtime existentes. El delivery transmite `delivery_location_update` con `order_id`, `latitude`, `longitude`, `accuracy`. El servidor obtiene usuario/asignación desde la sesión y base de datos.

La posición se publica exclusivamente a la unión de `order_<id>`, `user_<buyer>`, `business_<business>` y `delivery_<driver>`. Se revalidan las membresías antes de emitir. El comprador, administrador del negocio y delivery asignado acceden a `/orders/<id>/tracking` y al snapshot `/api/orders/<id>/tracking`. No se amplían permisos de superadmin ni de candidatos REV3.

El snapshot incluye pickup, dropoff, última posición, timestamp, estado y permiso de transmisión. Al entrar, reconectar o volver a foreground se recupera por HTTP con `no-store`; un control cada 15 segundos detecta revocaciones/cambios que se hayan perdido. Los eventos terminales cortan el GPS inmediatamente.

Leaflet crea el mapa una vez, ajusta bounds inicialmente y mueve únicamente el marker con `setLatLng`. Los tres puntos usan símbolos distintos. El estado pasa de espera a vivo y a última ubicación al superar 25 segundos. No se inventa movimiento ni se recentra el mapa en cada muestra.

## Estados y ciclo del GPS

Los estados reales siguen siendo `pending`, `shipped`, `delivered`, `cancelled`. Tracking activo significa `shipped` con delivery asignado. La aceptación existente ya cambia a `shipped`. `driver_arrived` significa llegada al cliente: **no** se interpreta como retiro en comercio. No existe una transición persistida de retiro; por eso no se afirma que el pedido ya fue retirado ni se inventan estados nuevos. Web Push de “en camino” usa la transición existente a `shipped`.

La aceptación abre el detalle del pedido. Solo el contexto de un pedido autorizado inicia `watchPosition`. Se ejecuta `clearWatch` al entregar, cancelar, perder asignación, desconectar, ocultar la app o salir de la página. Al volver se consulta nuevamente la autorización antes de reiniciar. El servidor rechaza posiciones posteriores a la entrega/cancelación, independientemente del navegador.

Máximo una muestra cada cinco segundos tanto en cliente como en servidor. Se mantiene también el límite Socket por cuenta existente. No se actualiza la posición global del usuario con el GPS de reparto. El dashboard ofrece un botón explícito de ubicación puntual para buscar solicitudes cercanas, conservando la disponibilidad REV3 sin seguimiento permanente.

## Persistencia y migración preparada

`migrations/006_delivery_tracking_web_push_prepared.sql` contiene exclusivamente SQL transaccional de creación, sin DROP/TRUNCATE. **No se ejecutó.**

- `order_delivery_locations`: una fila por pedido, clave primaria `order_id`; delivery emisor, coordenadas, precisión y timestamp. La fila se sobrescribe, sin historial. Una muestra de otro delivery no aparece tras reasignación. Se eligió tabla independiente para evitar cargar campos GPS en todas las consultas de pedidos y conservar separados los antiguos `delivery_latitude/longitude`, que carecían de timestamp/procedencia.
- `web_push_subscriptions`: una fila por endpoint de navegador, hash único, usuario y claves Push. Índice de usuario para altas/bajas/propiedad; borrado en cascada al eliminar el usuario.

La aplicación no aplica esta migración al arrancar. Antes de habilitar estas funcionalidades en otro entorno, la tabla de tracking y la tabla Push requieren la migración revisada por el operador. La creación de tablas en las bases aisladas de tests no ejecuta este SQL.

## Seguridad

Autenticación, usuario activo, rol delivery, asignación real y estado `shipped` se verifican antes de guardar GPS. Bloqueo de la fila del pedido serializa con los escritores de estado/asignación. Coordenadas y precisión deben ser números finitos dentro de rango; booleanos, null, strings, campos ajenos, IDs inválidos y payloads adicionales se rechazan. Fallos de commit hacen rollback y no publican posiciones.

Subscribe/unsubscribe/presence son POST autenticados con CSRF y rate limit. Nunca aceptan un `user_id` como autoridad. El endpoint tiene hash único y solo el usuario propietario puede eliminarlo. Cambiar la cuenta del mismo navegador exige las claves de la suscripción existente. Al cerrar sesión se elimina la suscripción de ese dispositivo.

Los endpoints de proveedores Push tienen validación HTTPS/host/puerto y longitud; no se siguen redirecciones HTTP. Las excepciones no registran endpoints, claves ni respuestas del proveedor. Las notificaciones del sistema llevan texto genérico, sin direcciones, coordenadas ni contenido privado del chat. Los enlaces se validan como internos en el worker; las rutas destino vuelven a comprobar autorización.

## Web Push

Eventos: nuevo pedido, chat de pedido y privado, solicitud de delivery, asignación, estado enviado/entregado/cancelado y notificación segmentada del superadmin. Los destinatarios se derivan de las mismas rooms privadas y se revalidan al enviar; no se envía el propio mensaje al emisor.

VAPID y cifrado estándar mediante `pywebpush`. Una cola local acotada de 100 trabajos y dos workers separa la red Push de las solicitudes de compra/chat; timeout de cinco segundos y TTL de 60 segundos. 404/410 eliminan la suscripción. Es entrega de mejor esfuerzo: la cola no es durable ni garantiza entrega si se reinicia el proceso o se llena; los datos originales de pedidos/chat/inbox permanecen en QuickGo.

Variables de entorno:

| Variable | Valor por defecto / propósito |
|---|---|
| `WEB_PUSH_ENABLED` | `false` |
| `WEB_PUSH_VAPID_PUBLIC_KEY` | Clave pública VAPID del operador |
| `WEB_PUSH_VAPID_PRIVATE_KEY` | Clave privada, exclusivamente en servidor |
| `WEB_PUSH_CONTACT` | Contacto VAPID, por ejemplo `mailto:` del operador |

Si faltan variables, Push permanece deshabilitado y no interrumpe Socket.IO ni el resto de la app. No hay claves operativas incluidas en el repositorio.

El botón “Activar notificaciones” pide permiso por acción del usuario. El worker `/sw.js` cubre `/` y conserva la política de cache de assets públicos. La presencia del dispositivo evita envíos Push cuando la app está visible y conectada; el worker agrega visibilidad de pestañas y evita notificaciones duplicadas en foreground. Los sonidos QuickGo solo se reproducen con la página visible. `event_id`, tags y deduplicación acotada protegen frente a repetidos; no hay garantía de exactamente una entrega ante reinicios/carreras del navegador.

## Límites de iOS/Android

No se promete GPS con pantalla bloqueada o JavaScript suspendido. Se conserva la última muestra y se muestra su antigüedad. Al recuperar foreground se verifica el pedido y se reinicia GPS si corresponde.

En iPhone el flujo soportado usa la app agregada a pantalla de inicio y una acción explícita para solicitar permiso. Sonido/vibración Push dependen del sistema operativo, permisos, silencio y DND; el audio personalizado QuickGo se conserva en foreground. Safari exige notificaciones visibles para Push: la presencia servidor reduce envíos que terminarían suprimidos en foreground, pero las carreras de suspensión/visibilidad siguen sujetas al navegador.

Fuentes: [WebKit: Web Push en iOS/iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/), [Apple: envío de Web Push](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers), [pywebpush](https://github.com/web-push-libs/pywebpush).

## Validación

Resultados finales existentes, revisados al retomar el trabajo:

| Validación | Passed | Failed |
|---|---:|---:|
| Python completa (`tracking-python-final.txt`) | 177 | 0 |
| JavaScript completa | 60 | 0 |
| Tracking Python (incluido en la suite) | 10 | 0 |
| Tracking JavaScript (incluido en la suite) | 6 | 0 |
| Push Python (incluido en la suite, VAPID/cifrado real con HTTP simulado) | 10 | 0 |
| Push JavaScript (incluido en la suite) | 5 | 0 |

Analytics: `/super-admin/analytics` devolvió HTTP 200 con datos vacíos, datos históricos opcionales nulos y productos de dos negocios. Roles no autorizados fueron rechazados. Se aprobaron también las pruebas existentes de transición post-login, themes, catálogo/SAMA, QuickGold, radio, negocio abierto/cerrado, inventario, chat, rooms de pedidos, candidatos REV3, destino, notificaciones segmentadas, CSRF, CSP y cache del worker.

A/B/C en Chrome: el comprador creó el pedido; el comercio lo recibió sin recarga; la solicitud se asignó/aceptó; tres posiciones simuladas llegaron a comprador y comercio con movimiento real del marker; al entregar las tres pantallas abandonaron live, el delivery ejecutó clearWatch y el servidor rechazó un envío posterior. Reporte sin errores JavaScript.

Visual: se revisaron capturas existentes del comprador a 390px y 1440px, comercio y delivery a 1440px, y comprador entregado a 390px. No hay desbordamiento horizontal. Pickup/dropoff/delivery y los dos enlaces de navegación son visibles. Waiting/stale y permisos de transmisión están verificados por tests; las capturas muestran live/delivered y el botón Push deshabilitado por configuración, no una entrega Push física.

`git diff --check`: limpio. No se repitió Python porque el resultado final era completo y posterior a los cambios Python. Se repitió JavaScript porque el archivo de ubicación puntual del delivery era posterior al registro anterior.

Reversión de la migración preparada: antes de COMMIT, un fallo debe resolverse con ROLLBACK. Después de una eventual aplicación por el operador, deshabilitar Push y volver a una versión compatible de la aplicación conserva estas tablas aditivas; no se incluye SQL destructivo. IF NOT EXISTS permite repetir la creación, pero no repara un esquema preexistente incompatible: el operador debe revisar ese caso. El script local de validación `tests/validate_tracking_browser.py` queda fuera del commit por indicación del usuario; las capturas y reporte JSON se generan en `tracking-validation/`, con usuarios ficticios y SQLite local de prueba. No se realizó prueba de entrega Push en dispositivos físicos iOS/Android ni con credenciales de producción.
