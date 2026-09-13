# QuickGo — modernización del negocio y catálogo

Entrega del 12 de septiembre de 2026. Rama: `feat/business-storefront-modernization`.
Base verificada y actualizada desde `origin/main`: `592f99b` (`Merge security REV3`).

Se trabajó en un worktree nuevo porque la carpeta original contenía cambios anteriores sin commit. Esos cambios se conservaron. No se modificó `main`, no se hizo merge ni se publicó la rama. No se accedió a Railway ni a datos de producción.

## Resultado

- Estado comercial `Business.is_open`, independiente de `is_active`. Los negocios existentes permanecen abiertos por defecto al aplicar la migración.
- Control visible para abrir/cerrar exclusivamente el negocio del administrador autenticado, mediante POST protegido por CSRF. Se rechazan identificadores ajenos y parámetros adicionales.
- Cierre validado al agregar productos y al confirmar el pedido. Si se cierra después de llenar el carrito, checkout lo rechaza con un mensaje claro y conserva carrito e inventario.
- Checkout mantiene los bloqueos de productos y añade bloqueo del negocio para coordinar el cierre con la transacción del pedido. Los precios históricos y el decremento de inventario siguen en la transacción existente.
- Cobertura obligatoria en producción, incluso si quedó desactivada la antigua bandera optativa de REV3. QuickGold conserva su excepción geográfica; también debe estar habilitado y abierto.
- Ubicación fija mediante un botón que solicita GPS una sola vez por pulsación. POST JSON con CSRF guarda únicamente `Business.latitude/longitude`; no modifica `User`. La dirección y el radio se guardan separadamente. Los antiguos POST de cobertura siguen siendo compatibles.
- Catálogo, detalle y destacados ya no muestran cantidades exactas de stock. El comerciante conserva su inventario privado. Se añadió la relación ORM `Product.business`, ausente aunque los templates ya la utilizaban.
- Actualización del catálogo mediante el Socket.IO existente y un evento nuevo que contiene únicamente estado público. La recuperación HTTP consulta ese mismo estado al reconectar, volver a la pestaña o cada 15 segundos. No se cambiaron rooms ni eventos privados.
- Login conservando autenticación, CSRF, recuperación, remember-me, errores y redirects. Paleta neutra con acentos dorados e iconos Bootstrap. Tarjetas de productos compactas, dos columnas móviles y seis en escritorio amplio; imágenes de 140 px con `object-fit: contain`.
- Fondo dorado perteneciente al contenedor. No se transforman destructivamente imágenes ni se añade eliminación de fondo o servicios pagos. Se mantiene la validación de uploads de REV3 para JPG/PNG/WEBP.
- Cuatro sonidos distintos. Pedido: pulso repetido y resolución aguda; chat: nota corta; entrega completada: intervalo ascendente; solicitud delivery: timbre triangular. Ganancias entre 0,09 y 0,22 y hasta cuatro eventos simultáneos: pico agregado máximo de 0,88. Se conserva desbloqueo tras interacción, silencio y deduplicación por identificador.

## Causa exacta del HTTP 500 de Analytics

La consulta original de productos más vendidos seleccionaba `Business.name` y agrupaba solamente por `Product.id`. PostgreSQL no admite esa selección sin agrupar el nombre del negocio o agregarlo.

Se extrajo la función original directamente del commit `592f99b`, se compilaron sus consultas ORM para PostgreSQL y se ejecutaron con datos sintéticos en PGlite 0.5.8 (PostgreSQL WASM local). Se reprodujo:

```text
42803 column "businesses.name" must appear in the GROUP BY clause or be used in an aggregate function
```

No se usaron logs ni una conexión de producción para esta reproducción. SQLite permitía la consulta original, por lo que la prueba exclusiva con SQLite no detectaba ese error.

La corrección agrupa explícitamente los identificadores y nombres seleccionados. También normaliza agregados con `coalesce`, serializa las etiquetas de gráficos con `tojson`, diferencia `order_count` de nombres propios de las filas ORM, incluye negocios sin ventas y reemplaza la distribución simulada por recuentos reales. Los productos vendidos requieren que el negocio del pedido coincida con el del producto: filas históricas inconsistentes no se atribuyen a otro comercio.

Analytics continúa siendo global y accesible exclusivamente para superadministradores. Comerciantes y usuarios delivery no pueden consultar ese informe.

## Migración preparada — SIN EJECUTAR

`migrations/005_business_open_prepared.sql` agrega `businesses.is_open BOOLEAN NOT NULL DEFAULT TRUE` con `ADD COLUMN IF NOT EXISTS`, dentro de una transacción. Es necesaria porque el estado comercial no puede reutilizar `is_active`.

No contiene DROP/TRUNCATE. No se añadió ejecución al arranque. Las migraciones `003_rev3_auth_prepared.sql` y `004_rev3_delivery_candidates_prepared.sql` permanecen intactas y no se ejecutaron.

## Validación

| Comprobación | Resultado |
| --- | --- |
| Suite Python existente durante revisión inicial | 120 pruebas, OK |
| Suite Python completa ampliada | 133 pruebas, OK, 721,304 s |
| Pruebas enfocadas después de añadir el caso de detalle cerrado | 14 pruebas, OK, 73,802 s |
| Todos los archivos `tests/*.test.cjs` | 40 pruebas, 40 aprobadas, ninguna omitida |
| PostgreSQL local: consultas ORM originales y corregidas | Error 42803 reproducido antes; cuatro consultas corregidas aprobadas |
| Casos PostgreSQL | Vacío, varios negocios, productos sin ventas, NULL históricos, cancelados y relación histórica entre negocios inconsistente |
| Revisión visual Edge, 390 y 1440 px | Login, catálogo abierto/cerrado, panel e inventario: sin desbordamiento horizontal; imágenes de 140 px, dos columnas móviles |
| Imágenes de prueba | PNG vertical, JPG horizontal/fondo oscuro y WEBP cuadrado, con dimensiones conservadas |
| `git diff --check` | Sin errores |

La suite completa incluye las pruebas preexistentes de REV3, QuickGold, cobertura, permisos, uploads, inventario/precios históricos, pedidos, chat y Socket.IO. Las nuevas pruebas cubren cierre durante checkout, CSRF/ownership, límites de coordenadas, ubicación fija, stock aislado, ausencia de stock público, Analytics y audio.

Las capturas revisan el HTML real y CSS; los scripts se verifican mediante las pruebas JS y HTTP/Socket.IO. No equivalen a una prueba de hardware GPS, altavoces físicos o carga concurrente sobre una instancia PostgreSQL nativa. La garantía de concurrencia conserva `SELECT FOR UPDATE` en productos y añade ese bloqueo al negocio; no se realizó una prueba de carga multiproceso.

Persisten avisos preexistentes de SQLAlchemy por relaciones antiguas y APIs obsoletas, y de `datetime.utcnow`. No son fallos de la suite.

## Archivos y motivo

| Archivo | Motivo |
| --- | --- |
| `.gitignore` | Excluir dependencias y utilidades de validación locales. |
| `models.py` | Estado comercial y relación bidireccional negocio/producto. |
| `security.py` | Bloquear compras en negocios cerrados y permitir visualizar el detalle cerrado. |
| `runtime_security.py` | Exigir cobertura en producción conservando la compatibilidad de fixtures locales. |
| `routes.py` | POST comerciales, ubicación fija, recuperación pública de estado, bloqueo transaccional y Analytics corregido. |
| `analytics_service.py` | Consultas agregadas portables y resultados normalizados. |
| `realtime.py` | Emitir únicamente estado comercial público después de confirmar el cambio. |
| `migrations/005_business_open_prepared.sql` | Preparar el cambio de esquema, sin ejecutarlo. |
| `static/css/storefront.css` | Paleta y densidad visual aplicadas progresivamente a las páginas modernizadas. |
| `static/js/business_location.js` | GPS explícito, CSRF y mensajes de estado accesibles. |
| `static/js/storefront_status.js` | Reutilizar socket y recuperar el estado comercial tras desconexiones. |
| `static/js/notifications_audio.js` | Timbres diferenciados, ganancia mayor y límite de voces simultáneas. |
| `templates/base.html` | Cargar iconos/estilos y permitir la clase visual de las páginas modernizadas. |
| `templates/login.html` | Login adaptable y accesible conservando el formulario actual. |
| `templates/admin/dashboard.html` | Controles de apertura, ubicación fija y radio; menos emojis. |
| `templates/admin/products.html` | Tarjetas compactas sin retirar stock privado ni acciones del propietario. |
| `templates/products.html` | Estado comercial, stock no numérico y presentación uniforme de productos. |
| `templates/product_detail.html` | Estado comercial y uso del filtro existente para imágenes locales/Cloudinary. |
| `templates/dashboard.html` | Compactar destacados y retirar stock numérico del comprador. |
| `templates/super_admin/analytics.html` | Gráficos con datos reales y serialización segura. |
| `tests/test_storefront.py` | Permisos, CSRF, cierre, cobertura, ubicación, inventario aislado y estado realtime. |
| `tests/test_storefront_analytics.py` | Acceso y render de Analytics con datos vacíos e históricos. |
| `tests/realtime.test.cjs` | Correspondencia evento/sonido y deduplicación al reconectar. |
| `tests/storefront_ui.test.cjs` | GPS manual, estado de catálogo y límites de audio. |
| `tests/export_analytics_sql.py` | Exportar consultas originales/corregidas sin acceder a producción. |
| `tests/analytics_postgres.cjs` | Reproducción y regresión de las consultas en PostgreSQL local. |
| `docs/STOREFRONT-ENTREGA.md` | Evidencia, alcance, archivos y pasos de activación. |

## Pasos manuales para Víctor

1. Revisar esta rama y el diff; no se hizo merge automático. Obtener su commit final con `git log -1 --format="%H %s"` en este worktree.
2. Probar primero en preproducción. Para reproducir cobertura también en un entorno marcado como testing/development, usar `SECURITY_ENFORCE_COVERAGE=true`.
3. Antes de desplegar este código en una base existente, aplicar manualmente **solamente** `005_business_open_prepared.sql`, mediante el procedimiento habitual de cambios de base. No repetir 003/004. Verificar la columna y su valor inicial con una consulta de solo lectura.
4. Desplegar únicamente después de esa migración y de la revisión de la rama. Este código consulta `is_open`; desplegarlo antes de crear la columna produciría errores de esquema.
5. En cada comercio, pulsar manualmente «Actualizar ubicación del negocio» desde el local real y comprobar dirección/radio. No se inspeccionaron ni corrigieron coordenadas reales. Una pareja errónea pero numéricamente válida debe corregirla su dueño.
6. Verificar con dos sesiones que cerrar bloquea un carrito anterior, abrir restablece compras dentro del radio y QuickGold sigue funcionando fuera del radio. Probar GPS y volumen en los dispositivos habituales tras una primera interacción.
7. Revisar `/super-admin/analytics` con el usuario superadministrador y datos del entorno elegido.

Rollback de aplicación: volver al commit previo si fuera necesario; dejar la columna adicional, compatible con el código anterior. No se propone una migración destructiva de reversión.

Cloudinary: el código existente sube imágenes ya validadas, sin transformaciones de fondo. No se consultó el plan de la cuenta ni sus credenciales; la solución CSS no depende de cuotas o funciones pagas.

## Reproducción local de la prueba PostgreSQL

Desde la raíz del worktree, usando un Python con las dependencias de pruebas instaladas:

```powershell
npm install --prefix .validation --no-audit --no-fund --ignore-scripts @electric-sql/pglite@0.5.8
python tests/export_analytics_sql.py > .validation/analytics-sql.json
node tests/analytics_postgres.cjs
```

Los datos se crean únicamente dentro de PostgreSQL WASM en memoria. La prueba no ejecuta la migración 005 y no necesita una URL de base de datos.
