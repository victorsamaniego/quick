# Entrega SAMA

Rama: `feat/public-catalog-notifications-style-fix`, creada desde `origin/main` (76f8876, PR #10 integrado). El commit de entrega se identifica con `git log -1 --format=%H`.

## Resultado

Catálogo y detalle públicos, búsqueda y ubicación de sesión coherentes, destino GET seguro al solicitar login para agregar al carrito. Se conservan cobertura, excepción QuickGold, negocio abierto/cerrado y validación privada de compras. El catálogo conserva el filtro previo de stock positivo; un detalle activo agotado puede consultarse y muestra Agotado. No se expone stock numérico al comprador.

Super Admin puede seleccionar cualquiera de las siete combinaciones de compradores, comercios y delivery. Hay validación de permisos, CSRF, campos y longitudes, persistencia por destinatario, bandeja y contador por rol, lectura por POST y auditoría de audiencias. Los eventos se publican después del commit en las rooms privadas existentes, reutilizan QuickRealtime y tienen deduplicación y tono de anuncio propio. La recuperación HTTP no suena.

La identidad visual vuelve a usar navbar oscura, marca SVG dorada, tarjetas claras con acentos dorados, ubicación destacada y estados vacíos compactos. Se mantienen imágenes de catálogo de 140px con contain y dos columnas móviles.

## Causa y reparación de iconos

La CSP de app.py permitía CSS desde jsDelivr en style-src, pero font-src solo permitía self, fonts.gstatic.com y unpkg.com. La hoja Bootstrap Icons de jsDelivr intentaba descargar su fuente desde ese CDN y el navegador la bloqueaba. Se reprodujo en Edge con la CSP exacta: violación font-src y fuente no cargada.

Ahora Bootstrap Icons 1.11.3, sus fuentes y licencia MIT se sirven localmente desde static/vendor/bootstrap-icons. No se amplía la CSP. La comprobación posterior no registra violaciones y confirma la fuente cargada. Además, bi-crown y bi-trending-up no existen en esa versión: se reemplazaron por bi-stars y bi-graph-up-arrow. El logo usa SVG inline. Se conserva el HTML/Jinja normal del fix de flash y el autoescape de mensajes dinámicos.

## Archivos y motivos

| Archivos | Motivo |
| --- | --- |
| routes.py | Ubicación pública consistente, detalle consultable, login seguro, endpoints y contexto de notificaciones. |
| security.py | Permitir consultar detalle agotado sin relajar los controles de compra. |
| notifications_service.py | Validación, audiencias, destinatarios persistidos y publicación después del commit. |
| static/css/storefront.css | Identidad dorada/oscura, ubicación, formularios, notificaciones y controles móviles. |
| static/images/product-placeholder.svg | Imagen local de respaldo del catálogo. |
| static/vendor/bootstrap-icons/bootstrap-icons.min.css, fonts/bootstrap-icons.woff, fonts/bootstrap-icons.woff2, LICENSE | Iconos locales compatibles con CSP y licencia del proveedor. |
| static/js/main.js | Evento de anuncio en la conexión compartida y filtro por audiencia. |
| static/js/notifications_audio.js | Tono diferenciado de anuncio. |
| static/js/notifications.js | Contador, bandeja, aviso, recuperación silenciosa y deduplicación. |
| static/sw.js | Nueva versión de caché y precarga de los recursos visuales locales. |
| templates/base.html | Fuente local, marca/navbar, indicador y script de notificaciones. |
| templates/products.html | Catálogo público, ubicación, búsqueda, tarjetas y estados vacíos. |
| templates/product_detail.html | Marca QuickGo, comercio visible y descripción opcional sin None. |
| templates/admin/home_stats.html, templates/super_admin/dashboard.html | Sustitución de dos clases de iconos inexistentes. |
| templates/super_admin/create_notification.html | Selección independiente de las tres audiencias. |
| templates/super_admin/notifications_list.html, templates/super_admin/view_notification.html | Auditoría con etiquetas de audiencias combinadas. |
| templates/user_notifications.html, templates/view_notification_user.html | Bandeja integrable con realtime y lectura explícita protegida por CSRF. |
| tests/test_sama.py | Regresiones de catálogo, cobertura, permisos, siete combinaciones, aislamiento, CSRF e iconos. |
| tests/notifications_ui.test.cjs, tests/realtime.test.cjs | Recuperación silenciosa, DOM seguro y deduplicación de notificaciones/sonido. |
| tests/security_sw.test.cjs | Verificar eliminación de las dos versiones antiguas de caché. |
| docs/SAMA-ENTREGA.md | Evidencia, alcance y pasos de revisión. |

## Base de datos

No se creó migración 006: Notification.notification_type ya admite 50 caracteres y las audiencias canónicas combinadas ocupan como máximo 26. Se reutilizan Notification y NotificationRecipient, manteniendo lectura de tipos individuales y all anteriores. No se modificaron modelos, migraciones, app.py ni analytics_service.py. No se ejecutó ninguna migración.

## Validación

Suite Python completa: **143 tests OK**, 853.139 segundos, sin fallos. JavaScript: **43 tests OK**, sin fallos ni omitidos. Comandos: `python -m unittest discover -s tests -v` y `node --test tests/*.test.cjs` (en PowerShell, expandiendo los archivos). La corrección final de descripción/comercio en la plantilla se verificó además mediante nuevo renderizado y capturas de navegador.

Analytics: ruta real GET /super-admin/analytics devuelve 200. Las cuatro consultas existentes pasaron el ensayo PostgreSQL WASM/PGlite, incluyendo casos vacíos, múltiples negocios y datos inconsistentes; la consulta anterior reproduce 42803. No se reescribieron consultas de Analytics.

Edge a 390px y 1440px: home, catálogo, detalle, login, dashboard comercio, productos admin, Super Admin, creación de notificaciones, bandeja y estado vacío (20 capturas). Comprobación de ancho sin overflow, fuente cargada, iconos definidos y dos columnas de catálogo; inspección visual de las capturas. Se usaron plantillas reales y datos/imágenes sintéticos. Los scripts externos se deshabilitaron en la prueba de layout: esto no certifica la ejecución visual de gráficos. El comportamiento JavaScript se verifica por separado.

La aplicación Flask real también respondió 200 para home, productos, detalle, login y los tres recursos CSS/fuentes locales. Scripts, logs y capturas de validación están en .validation/, ignorado y fuera del commit.

## Límites y pasos manuales para Víctor

1. Revisar el commit y las capturas locales antes de autorizar integración o despliegue.
2. En un entorno de pruebas, abrir una sesión por rol y enviar notificaciones a cada grupo y a combinaciones; comprobar bandeja, contador y lectura.
3. Activar audio mediante interacción y comprobar el tono en un dispositivo real. Autoplay y GPS físico dependen de permisos del navegador y no se verificaron con hardware.
4. Después de un despliegue autorizado, cerrar y reabrir las ventanas de la PWA para que se active el service worker actualizado; comprobar las fuentes locales en Network.

La recuperación HTTP automática trae las 50 notificaciones más recientes; la bandeja persistida permite consultar el historial completo. El envío resuelve los usuarios activos en memoria y no se ha medido rendimiento con un padrón masivo. PostgreSQL se validó localmente con PGlite, no contra producción.

No hubo merge, despliegue, acceso a Railway/producción, cambio de secretos, borrado de datos ni servicios pagos. Esta entrega queda en la nueva rama local; no se realizó push ni se modificó PR #10.
