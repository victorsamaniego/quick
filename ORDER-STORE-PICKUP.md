# Retiro presencial de pedidos

## Base y diseño

Rama `feat/order-store-pickup`, creada desde `origin/main` actualizado, commit
`5e1d33c` (merge del PR #15). Trabajo aislado en `pickup-worktree`; los cambios
preexistentes del checkout original no se incorporaron.

`Order.status` es un `String(20)`, no un enum de PostgreSQL. Se agrega `picked_up`,
mostrado como **Retirado del local**, distinto de `delivered`.
No existe un historial de transiciones de Order. `updated_at` no es una evidencia
estable del retiro porque puede cambiar posteriormente; `delivered_at` identifica
entregas. Se agrega `picked_up_at`, nullable, con zona horaria y escritura en UTC.

## Endpoint y seguridad

Nuevo `POST /admin/orders/<order_id>/pick-up` (`admin.pick_up_order`):

1. Reutiliza login, `business_admin_required`, `subscription_required`, CSRF
   global y límites globales, como la ruta equivalente de actualización.
2. Bloquea la fila del pedido y carga su estado fresco.
3. Compara `order.business_id` con `current_user.business_id`; ignora IDs de negocio
   enviados por navegador. Devuelve 403 para otro negocio habilitado y 404 si no existe.
   Los usuarios sin rol vendedor conservan la redirección del decorador existente.
4. Solo permite `pending`, sin delivery asignado. Cualquier otro estado devuelve 409.
5. Bloquea búsquedas de delivery pendientes no vencidas con un mensaje explícito.
   Una solicitud sin vencimiento tampoco se considera segura para retiro.
6. Guarda estado y timestamp, hace commit, publica el evento y devuelve JSON.
   Un fallo de persistencia revierte la transacción y no publica cambios.

El endpoint general `update-status` no puede reabrir un pedido `picked_up`.
El endpoint de entrega del delivery tampoco puede convertirlo a `delivered`.
Los flujos de confirmación del comprador y aceptación de delivery mantienen sus
precondiciones existentes. El despacho tradicional adquiere los bloqueos en el
orden pedido → solicitud, compatible con retiro y con el despacho de candidatos.

## Realtime, Push y tracking

- `publish_status` sigue enviando `order_status_update` a las rooms actuales
  `order_ID`, `user_ID` y `business_ID`. No se crea otro transporte.
- `publish` emite Socket.IO antes de encolar Web Push; ambos ocurren después del
  commit. Conserva el funcionamiento de Push cuando Socket.IO no está inicializado.
- El comprador y vendedor refrescan fragmentos mediante `QuickRealtime.refreshOrders`.
  La acción también refresca después de recibir éxito HTTP. Los detalles del comprador
  se renuevan; se conserva la espera existente cuando hay un modal abierto.
- Push usa `web_push.enqueue`, el mismo proveedor, permisos, deduplicación de audio
  y `WEB_PUSH_ENABLED`. Título: “Pedido retirado”; cuerpo con número del pedido.
- `Order.tracking_active` exige `shipped` y delivery asignado; por eso `picked_up`
  rechaza GPS en `save_location`, tanto desde HTTP como desde Socket.IO.
  El frontend detiene el GPS al recibir el estado y muestra “Retirado del local”.
- El retiro no asigna ni libera drivers. No aparece en entregas activas, y ninguna
  variante del despacho puede aceptar el pedido posteriormente.
- El chat conserva el historial y bloquea nuevos mensajes igual que otros estados finales.

## Interfaz y estadísticas

La acción usa el estilo existente negro/dorado, confirmación explícita y CSRF.
Se deshabilita durante el envío y después del éxito. El vendedor tiene un filtro
“Retirados”. Las vistas que usan `Order.status_label` incluyen automáticamente
comprador, vendedor y Super Admin; los gráficos muestran la etiqueta legible.

Ventas, productos vendidos e ingresos comerciales incluyen `delivered` y `picked_up`.
La distribución por estado mantiene ambos grupos separados. Ganancias, cantidades y
ranking de deliveries siguen contando únicamente `delivered`. El retiro no recalcula
pagos, totales, comisiones, stock ni cargos de envío existentes.

## Archivos

- `models.py`: timestamp, etiqueta, color e ingresos del negocio.
- `routes.py`: endpoint, validación de finalización, bloqueo de despacho, consultas de ventas y cierre de chat.
- `analytics_service.py`: ventas y etiquetas de estadísticas globales.
- `realtime.py`, `web_push.py`: orden de transportes y contenido de Push.
- `static/js/order_pickup.js`: confirmación y envío de la acción.
- `static/js/main.js`: sonido de finalización y refresco de detalles del comprador.
- `static/js/delivery_tracking.js`: texto de retiro al finalizar tracking.
- `templates/admin/orders.html`: acción, filtro, timestamp y controles finales.
- `templates/admin/dashboard.html`: etiqueta y color de retiro en gráfico.
- `templates/dashboard.html`: timestamp y notificación legible del comprador.
- `templates/chat/order_chat.html`: cierre para retiro.
- `templates/super_admin/analytics.html`: etiquetas de estados.
- `migrations/007_order_store_pickup_prepared.sql`: nueva columna idempotente.
- `tests/test_order_pickup.py`, `tests/order_pickup.test.cjs`: nuevas pruebas.
- `tests/realtime.test.cjs`, `tests/delivery_tracking.test.cjs`: regresiones de sonido y GPS.

## Migración manual: preparada, NO ejecutada

Revisar `migrations/007_order_store_pickup_prepared.sql`. No requiere convertir
estados existentes. Ejecutarla manualmente **antes** de desplegar esta versión:

```sql
BEGIN;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS picked_up_at TIMESTAMPTZ;
COMMIT;
```

Ejemplo desde la raíz de la rama, con una conexión elegida y autorizada por el operador:

```text
psql "<CONEXION_POSTGRESQL_REVISADA>" -v ON_ERROR_STOP=1 -f migrations/007_order_store_pickup_prepared.sql
```

Verificación manual posterior:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'orders' AND column_name = 'picked_up_at';
```

Debe informar `timestamp with time zone`. El `ALTER TABLE` toma un bloqueo: programar
su aplicación según la operación del negocio. Una reversión de código debe conservar
la columna y los estados ya registrados para no perder la distinción histórica.
No ejecutar una reversión que vuelva a permitir tomar pedidos retirados.

## Validación

Comandos de las suites del repositorio:

```text
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
```

Se utilizó el Python del entorno local `security-venv`, con las fixtures aisladas SQLite,
sin importar la configuración de producción. Logs fuera del repositorio, en TEMP.
Las pruebas nuevas verifican permisos e IDOR, CSRF, estados inválidos, persistencia UTC,
reintentos, rollback, commit previo a emisión, rooms, Push, GPS, ambas variantes de
aceptación, vistas y separación de ventas/delivery. JavaScript prueba confirmación,
conflictos, repetición, refresco, sonido único y detención de tracking.

Resultados finales (15/09/2026):

- Python completo: **189 tests, OK**, 666,782 segundos; cero fallos y errores.
- JavaScript completo: **66 tests aprobados**, cero fallos, cancelados u omitidos.
- Python específico de retiro: **12 tests, OK**.
- Se agregaron 12 pruebas Python y 6 JavaScript sobre la base de main.
- `git diff --check`: aprobado.
- Una corrida completa anterior también pasó: 188 tests, antes de incorporar
  la última prueba de candidatos y completar los ajustes finales.
- La suite muestra advertencias existentes de SQLAlchemy y `datetime.utcnow`;
  no afectan el resultado. No se ejecutaron auditorías de dependencias, Docker ni
  el helper opcional PostgreSQL/WASM, que no forman parte de estos comandos de tests.

## Límites de verificación

SQLite no prueba los bloqueos reales de PostgreSQL. No se ejecutó la migración,
ni se conectó a Railway/PostgreSQL, ni se envió Push a dispositivos reales.
No se hizo merge, deploy ni modificación de datos reales.
