# QUICKGO — Informe para revisión manual

Fecha: 22/09/2026.

## 1. Rama y alcance

- Worktree exclusivo: `C:\Users\Sama\Documents\quick-merchant-approval`.
- Rama: `feat/merchant-approval-catalog-ux`.
- Base verificada: `d3d4ab8f9aa7bc237ed128848756267d1e70de68` (`origin/main`).
- Se aceptó el fetch y la creación manual del worktree confirmados por el usuario; se verificó estado limpio antes de editar.
- Los cambios quedan sin staging y sin commit. No se ejecutó merge, push, despliegue, migración ni operación contra producción. No se modificó el checkout original.

## 2–3. Implementación y problemas encontrados

Se integran aprobación manual, notificación del Super Admin, imágenes de catálogo, documentos legales y búsqueda instantánea.

Problemas previos corregidos:

- El registro asignaba `user.business_id = new_business.id` antes de persistir el negocio. Ahora asigna `user.business = new_business`, dentro de la transacción del registro.
- Ser administrador era suficiente para entrar en rutas comerciales; no existía estado explícito de aprobación. El nuevo guard central se ejecuta antes de las operaciones HTTP.
- `/api/products/search` ya existía, pero omitía negocios activos y cobertura/QuickGold. Ahora comparte consulta SQL y cálculo geográfico con `/products`.
- Las imágenes del catálogo repetían markup y usaban fondos decorativos; ahora tienen macro y servicio únicos.
- El registro no exigía aceptación legal.

## 4–6. Archivos y motivo

`M`: archivo existente modificado. `N`: archivo nuevo.

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `forms.py` | Consentimiento obligatorio validado por WTForms. |
| M | `models.py` | Estado controlado de aprobación, auditoría, consentimiento y relaciones FK explícitas. |
| M | `realtime.py` | Rechazo de conexiones/salas/pedidos para comerciantes no aprobados. |
| M | `routes.py` | Asociación de registro, guard central, páginas legales, solicitudes/decisiones, contador y búsqueda con cobertura compartida. |
| M | `security.py` | Impide acceso público o compra de productos de negocios no aprobados. |
| M | `socket_security.py` | Impide operaciones Socket.IO de comerciantes no aprobados. |
| M | `templates/base.html` | Footer legal, fallback de imágenes y navegación mínima para pendientes/rechazados. |
| M | `templates/dashboard.html` | Presentación pública de destacados con macro central de imágenes. |
| M | `templates/product_detail.html` | Imagen uniforme del detalle y fallback. |
| M | `templates/products.html` | Buscador instantáneo accesible y macro de imagen; mantiene GET. |
| M | `templates/register.html` | Checkbox sin marcar y enlaces legales. |
| M | `templates/super_admin/dashboard.html` | Campana/tarjeta visible con contador calculado desde DB. |
| N | `migrations/009_merchant_approval_catalog_prepared.sql` | Migración PostgreSQL preparada; estado/auditoría e historial de aceptación. |
| N | `product_images.py` | Construye URLs derivadas con SDK 1.41.0 sin llamadas de red. |
| N | `static/css/product_live_search.css` | Resultados adaptables a móvil y foco visible. |
| N | `static/js/product_images.js` | Carga derivada, original y placeholder con reintentos acotados. |
| N | `static/js/product_live_search.js` | Debounce, cancelación, rechazo de respuestas obsoletas y teclado sin innerHTML. |
| N | `templates/legal/layout.html` | Estructura y pendientes jurídicos explícitos; canal público de contacto por definir. |
| N | `templates/legal/privacy.html` | Política pública basada en funciones existentes y revisión jurídica pendiente. |
| N | `templates/legal/terms.html` | Términos públicos sin inventar decisiones comerciales. |
| N | `templates/macros/product_image.html` | Macro única de tamaño, fondo blanco, original y derivada. |
| N | `templates/merchant_status.html` | Pantalla de espera/rechazo con cierre de sesión. |
| N | `templates/super_admin/merchant_request_detail.html` | Datos del solicitante, decisiones POST, motivo e historial de decisión. |
| N | `templates/super_admin/merchant_requests.html` | Lista paginada por estado con contacto y acceso al detalle. |
| N | `tests/merchant_feature_support.py` | Fixtures aisladas con SQLite, CSRF, templates y limitador reales. |
| N | `tests/product_catalog_ux.test.cjs` | Cinco pruebas JS de debounce, XSS, teclado, errores y fallback. |
| N | `tests/test_legal_pages.py` | Acceso público, footer, checkbox y rechazo de registro sin aceptación. |
| N | `tests/test_merchant_approval.py` | Registro, asociación, roles, auditoría, POST/CSRF, estados, contador y Socket.IO. |
| N | `tests/test_product_images.py` | SDK/URLs, originales antiguos, uploads simulados y fallos. |
| N | `tests/test_product_live_search.py` | Longitud, coincidencias, stock, cobertura, QuickGold, datos públicos y rate limit. |
| N | `docs/MERCHANT-APPROVAL-CATALOG-REVIEW.md` | Informe final para auditoría manual y límites de validación. |

## 7–10. Migración, estados y protección

**MIGRACIÓN REQUERIDA: SÍ**

Archivo: `migrations/009_merchant_approval_catalog_prepared.sql`. Preparada, **no ejecutada**. Debe revisarse y aplicarse manualmente antes de usar esta versión con una base existente.

- `businesses.approval_status`: `pending`, `approved`, `rejected`, con CHECK e índice.
- Auditoría: `approved_at`, `approved_by_user_id`, `rejected_at`, `rejected_by_user_id`, `rejection_reason` (máximo 300 caracteres).
- `users.legal_accepted_at` y `users.legal_version` para nuevos registros.
- Default/backfill de negocios preexistentes: `approved`, sin modificar `is_active`, suscripciones, radio, QuickGold, comisiones ni caja. Campos de auditoría antiguos quedan NULL; no se inventa una decisión histórica.
- Aceptación de usuarios preexistentes queda NULL; no se atribuye consentimiento retroactivo.
- Las nuevas solicitudes públicas especifican `pending` e `is_active=False`. Los negocios creados por Super Admin conservan el comportamiento anterior.

El usuario pendiente puede autenticarse. Su destino se fuerza a `/merchant/status`, incluso con `next` manipulado. El guard permite exclusivamente estado, login/transición, logout, documentos legales y recursos estáticos/manifest/worker. Otras páginas redirigen a estado; operaciones y APIs reciben 403 (o CSRF 400 cuando falta token). No se muestran menús operativos. Socket.IO también impide conexión, salas y eventos.

Las decisiones requieren login, Super Admin, POST y el CSRF global existente. Los endpoints no toman el estado ni el aprobador desde formularios. Sólo transicionan desde `pending` mediante UPDATE condicional; una decisión repetida/ya resuelta devuelve 409. Un ID inexistente devuelve 404. Se valida el propietario comercial asociado.

Aprobar marca `approved`, activa el negocio y registra actor/fecha. Rechazar marca `rejected`, desactiva y registra actor/fecha/motivo sin borrar usuario ni negocio. No cambia suscripción: un aprobado sigue sujeto al mecanismo de activación existente. No se implementa reapertura de decisiones ya resueltas.

## 11. Notificación de solicitudes

El dashboard muestra tarjeta/campana y badge con `COUNT` de negocios `pending`. Se actualiza al recargar y enlaza la lista paginada (30 por página), con filtros controlados. Lista y detalle muestran negocio, registro y contacto; el detalle contiene las acciones. No se añadió Web Push ni un nuevo canal de notificación en tiempo real.

## 12–13. Cloudinary y degradación

Se utiliza el SDK declarado `cloudinary==1.41.0`; se comprobó localmente la cadena generada:

`e_background_removal/b_white,c_pad,g_center,h_600,w_600/f_auto,q_auto`

El original almacenado no cambia. El upload existente de creación/edición se conserva: sólo se transforma la presentación pública (catálogo, detalle, destacados y autocomplete). Las URLs estándar HTTPS de `res.cloudinary.com/.../image/upload/` pueden transformarse, incluidas antiguas. URLs firmadas, ya transformadas o no compatibles se conservan; rutas locales siguen disponibles. URLs inválidas/no seguras reciben placeholder.

La derivada se solicita desde el navegador. Error 423 o cualquier fallo de carga: original; si también falla: placeholder, sin ciclo infinito. Sin JavaScript queda el original. Un error del SDK al construir la URL devuelve el original y no bloquea el registro del producto.

No hubo llamadas reales a Cloudinary en pruebas: uploads mockeados y respuestas 423/original simuladas en navegador. Habilitación, coste, límites y calidad efectiva de eliminación requieren validación de la cuenta antes de uso comercial. No se modificaron credenciales ni se añadió proveedor.

Fuente técnica: [Cloudinary Background Removal](https://cloudinary.com/documentation/background_removal), que documenta la derivada no destructiva, 423 temporal y consumo especial de transformaciones.

## 14–15. Privacidad, términos y aceptación

`/privacy` y `/terms` son públicos y están en el footer. Cubren datos, ubicación autorizada, pedidos, participantes, proveedores existentes, conservación, seguridad, derechos, responsabilidades y cambios. Se considera la Ley paraguaya 7593/2025 sin declarar cumplimiento absoluto ni fijar fechas jurídicas no verificadas.

El registro exige `BooleanField` + `DataRequired` y validación del servidor. No viene marcado. Se registra fecha UTC y versión `2026-09-22` únicamente tras la aceptación. No hay tracking nuevo.

**Pendiente empresarial/jurídico explícito:** identidad legal y domicilio del operador, contacto público accesible sin login, plazos de conservación, bases jurídicas/transferencias, cancelaciones/reembolsos y mecanismos de reclamación/suspensión. Se requiere revisión por asesor jurídico antes del lanzamiento comercial definitivo; está indicado en comentarios y en las páginas. No se inventó un email ni un canal de soporte para compradores que el código no ofrece.

Referencia consultada: [Biblioteca del Congreso — Ley 7593/2025](https://www.bacn.gov.py/leyes-paraguayas/12924/ley-n-75932025-de-proteccion-de-datos-personales-en-la-republica-del-paraguay). La búsqueda oficial devolvió el texto; la apertura directa respondió 403. El informe no certifica vigencia/reglamentación ni cumplimiento legal.

## 16–17. Búsqueda y cobertura

- GET `/api/products/search?q=...`, límite 200 caracteres, trim, mínimo 2 y 120 solicitudes/minuto/IP.
- Máximo 10 productos, activos y con stock; negocio activo y aprobado.
- Reutiliza `obtener_negocios_cercanos` y `catalog_products_query`; respeta radio, coordenadas guardadas, ubicación de referencia existente, QuickGold y categoría.
- Un comercio cerrado sigue visible igual que en el catálogo; el control de compra existente impide operar mientras está cerrado.
- JSON sólo contiene ID público, nombre, precio de venta, imagen derivada/original para fallback, comercio y URL pública; no incluye coste, margen, teléfonos ni datos administrativos.
- Debounce 300 ms, `AbortController` y número de generación para descartar respuestas tardías. Enlaces nativos enfocables con Tab/Enter; flechas y Escape. Estado accesible y atributos ARIA.
- Se crean nodos y se usa `textContent`. El formulario GET y botón Buscar siguen funcionando sin JavaScript o ante errores de la búsqueda instantánea.

## 18–20. Pruebas y resultados

Se ejecutaron primero los tests nuevos y luego las suites completas, con variables de proceso aisladas y SQLite en memoria. Los tokens/credenciales de prueba son efímeros; no se utilizaron datos reales.

| Ejecución | Resultado exacto |
| --- | --- |
| Nuevos Python: `python -m unittest -v test_merchant_approval test_legal_pages test_product_images test_product_live_search` (raíz y tests en PYTHONPATH) | 21 tests, 69.659 s, OK, salida 0 |
| Nuevos JS: `node --test tests/product_catalog_ux.test.cjs` | 5 tests, 5 pass, 0 fail, salida 0 |
| Python completa: `python -m unittest discover -s tests -v` | 225 tests, 822.184 s, OK, salida 0 |
| JS completa: `node --test tests/*.test.cjs` | 71 tests, 71 pass, 0 fail, 0 skipped, salida 0 |
| `python -m pip check` | No broken requirements found, salida 0 |
| Análisis sintáctico Python de archivos cambiados y UTF-8 sin BOM | OK para los 31 archivos entregados |

Las suites conservaron warnings previos de SQLAlchemy y deprecaciones; no hubo fallos. Evidencia local ignorada por Git: `.validation/feature-python.log`, `.validation/full-python.log` y `.validation/browser-results.json`.

Chrome headless, móvil 390×844 y escritorio 1366×900: búsqueda real con debounce, flecha/Enter al producto, imagen 423 simulada con fallback al original, pantalla pendiente y URL directa bloqueada, navegación privacy/terms, aprobación POST y contador 1→0. Resultado final: todos los pasos pasaron, `pageErrors: []`. Se inspeccionaron visualmente capturas de buscador móvil, estado pendiente y detalle de solicitud. El servidor temporal quedó detenido.

Durante la preparación de la prueba visual se corrigieron dos problemas del fixture, sin cambiar la aplicación: una respuesta 423 simulada contenía por error una imagen decodificable, y el contexto global de Flask del servidor de prueba persistía entre sesiones. El recorrido final se ejecutó con cuerpo de error realista y contextos de solicitud separados. Las pruebas de navegador no validan la infraestructura de producción.

## 21–22. Integridad y estado final

`git diff --check`: salida 0, sin errores de whitespace. Git advierte que su configuración de Windows puede convertir LF a CRLF al tocar los archivos; no es un fallo del diff. Archivos editados en UTF-8 sin BOM.

Rama final: `feat/merchant-approval-catalog-ux`. HEAD sigue en `d3d4ab8f9aa7bc237ed128848756267d1e70de68`. Staging vacío. **12 archivos existentes modificados y 19 nuevos**, todos sin commit.

Estado final (`git status --short --untracked-files=all`):

```text
 M forms.py
 M models.py
 M realtime.py
 M routes.py
 M security.py
 M socket_security.py
 M templates/base.html
 M templates/dashboard.html
 M templates/product_detail.html
 M templates/products.html
 M templates/register.html
 M templates/super_admin/dashboard.html
?? docs/MERCHANT-APPROVAL-CATALOG-REVIEW.md
?? migrations/009_merchant_approval_catalog_prepared.sql
?? product_images.py
?? static/css/product_live_search.css
?? static/js/product_images.js
?? static/js/product_live_search.js
?? templates/legal/layout.html
?? templates/legal/privacy.html
?? templates/legal/terms.html
?? templates/macros/product_image.html
?? templates/merchant_status.html
?? templates/super_admin/merchant_request_detail.html
?? templates/super_admin/merchant_requests.html
?? tests/merchant_feature_support.py
?? tests/product_catalog_ux.test.cjs
?? tests/test_legal_pages.py
?? tests/test_merchant_approval.py
?? tests/test_product_images.py
?? tests/test_product_live_search.py
```


## 23. Riesgos y pendientes

- Migración preparada, no ejecutada ni validada contra un servidor PostgreSQL. Las pruebas usan SQLite en memoria. Revisar respaldo/ventana y aplicar manualmente antes de arrancar esta versión con una base existente.
- Los negocios históricos se preservan como aprobados. Solicitudes antiguas incompletas u usuarios sin negocio por el bug previo requieren auditoría manual; no se repararon datos reales ni se dedujo estado a partir del nombre.
- Las decisiones concurrentes se protegen con actualización condicional; se probaron decisiones repetidas, no una carrera real en PostgreSQL.
- La revisión jurídica y los datos empresariales señalados siguen pendientes.
- La eliminación efectiva de fondos, costes y permisos de Cloudinary no se comprobaron contra una cuenta real. El fallback fue probado con mocks y navegador.
- Validación local en Windows/Python y Chrome. Docker no estaba disponible en PATH; no se ejecutó imagen de producción, Gunicorn, gevent ni PostgreSQL. Se instalaron en `.venv` las dependencias de aplicación necesarias para las pruebas; `requirements.txt` no se modificó.
- Se conservaron los warnings previos de SQLAlchemy; no se reescribieron funciones ajenas para silenciarlos.
- `.venv/` y `.validation/` contienen únicamente herramientas/evidencia locales ignoradas por Git. No deben formar parte del cambio a publicar.
