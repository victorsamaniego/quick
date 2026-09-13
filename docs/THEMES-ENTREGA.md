# Entrega: UI interna, temas y login QuickGo

Rama: `feat/internal-themes-login-motion`.
Base verificada después de `git fetch origin`: `2ac302d46b7b42dedb9f32fb0b31fb54d05d3807` (`origin/main`, merge del PR #11/SAMA). Trabajo aislado en `themes-worktree`; no se modificaron los worktrees anteriores.

## Configuración: causa y solución

`/account/settings` ya existía y el enlace del menú era correcto. La ruta redirigía a `/dashboard` cuando `current_user.is_admin` o `current_user.is_delivery` era verdadero. Esto bloqueaba a comercios, delivery y al Super Admin con `is_admin` habilitado. No era un endpoint ausente. Además, aceptaba cualquier valor de tema y el script de preview reemplazaba todas las clases del body.

La ruta ahora permite a cualquier usuario autenticado gestionar exclusivamente su apariencia. Solo acepta un campo `theme` de la whitelist exacta, además del token CSRF; rechaza campos adicionales, duplicados y parámetros de consulta. El usuario se determina siempre desde `current_user`. La vista previa cambia únicamente la clase de tema y no persiste nada hasta enviar el formulario.

## Persistencia y arquitectura

Se reutiliza `User.theme_color` (String(20)). No hay columna nueva ni migración. Las cuatro claves son `gold-classic`, `dark-gold`, `black-gold` y `sand`.

El valor previo `gold`, valores vacíos o antiguos no soportados se presentan como Gold Classic; `oscuro` se presenta como Dark Gold. La normalización no escribe ni transforma masivamente datos existentes. Al guardar se persiste la clave canónica en el mismo campo, y se vuelve a leer al iniciar sesión. El default efectivo es Gold Classic, aunque el default histórico del modelo sigue siendo `gold`.

`base.html` aplica `qg-internal` y la clase de tema a las páginas autenticadas internas. Home, catálogo, detalle público, registro y login quedan fuera de esta personalización. El catálogo SAMA conserva su diseño. `themes.css` concentra las variables y la adaptación de cards, tablas, formularios, navegación, dropdowns, footer, mensajes y alertas. Los overrides con `!important` son una capa de compatibilidad con Bootstrap y los estilos anteriores; no se repartieron paletas entre templates.

Las superficies Gold Classic son crema sobre fondo dorado dominante; Dark Gold usa gris cálido, Black Gold negro y Sand arena. Éxito y cerrado/error conservan verde y rojo. Las etiquetas de los gráficos del comercio leen las variables de texto y borde; sus datos, cálculos y eventos permanecen iguales.

## Login

Se conserva el formulario WTForms, CSRF, usuario/email, contraseña, botón mostrar/ocultar, recordar sesión, errores, recuperación y registro. No se modificó la función de autenticación ni la validación de next.

Quick entra con opacity/translateY durante 650ms. Go comienza a los 300ms, realiza un impulso suave de 700ms y un brillo que termina a los 1150ms. Después queda estático. No tiene animación infinita, no bloquea el formulario y no introduce dependencias. `prefers-reduced-motion: reduce` elimina las animaciones y el brillo. Las transformaciones no cambian el espacio del formulario.

## Archivos modificados y motivo

| Archivo | Motivo |
| --- | --- |
| themes.py | Whitelist y normalización de preferencias existentes. |
| app.py | Normalizar current_theme en el context processor real. |
| routes.py | Contexto de tema y corrección segura de account_settings para todos los roles. |
| templates/base.html | Aplicar clase interna y cargar CSS central conservando el catálogo público. |
| templates/account_settings.html | Cuatro tarjetas seleccionables, preview y POST con CSRF. |
| static/js/theme_settings.js | Preview sin borrar clases ni persistir por una segunda vía. |
| static/css/themes.css | Variables de las cuatro paletas y componentes internos. |
| templates/login.html | Marca animada y CSS externo, conservando el formulario y su lógica. |
| static/css/login.css | Login negro/dorado, animación breve y movimiento reducido. |
| templates/admin/dashboard.html | Color legible para etiquetas y ejes de los gráficos. |
| templates/chat/order_chat.html | Retirar un fondo inline que impedía tematizar el chat. |
| templates/user_messages.html | Icono Bootstrap local consistente en el título. |
| static/sw.js | Versión de caché v4 y recursos de apariencia explícitos; páginas privadas siguen usando red. |
| tests/test_themes.py | Acceso por rol, Super Admin, CSRF, whitelist, propiedad, persistencia, default, clases, login y aislamiento público. |
| tests/themes.test.cjs | Preview conserva clases, valida valores y no tiene transporte de persistencia. |
| docs/THEMES-ENTREGA.md | Alcance, evidencia y pasos de revisión. |

## Validación

Suite Python completa: **150 tests passed, 0 failed**, en 1178.423 segundos. Suite JavaScript completa: **44 tests passed, 0 failed**, sin omitidos. Además, las siete pruebas específicas de temas pasaron de forma aislada. Comandos: `python -m unittest discover -s tests -v` y `node --test` con todos los archivos `tests/*.test.cjs`. La aplicación Flask real confirmó GET/POST de Configuración para Super Admin, CSRF, persistencia de Dark Gold y Analytics HTTP 200. Scripts y evidencias locales permanecen en `.validation/`, ignorada y fuera del commit. La suite completa conserva las pruebas SAMA/REV3, Analytics, cobertura, inventario, precios históricos, notificaciones y realtime.

La revisión de navegador completó **58 combinaciones de pantalla/tamaño**, más 8 capturas de dropdown y comprobaciones de movimiento reducido. Usa Edge, plantillas reales y datos sintéticos a 390px y 1440px. Las siete pantallas internas (dashboard comercio, productos admin, inventario, Super Admin, Configuración, notificaciones y mensajes) se verifican en cada paleta; login tiene su propia paleta fija. Se comprueban ancho, fuente local, iconos, color efectivo del fondo y superficies. Hay capturas adicionales del dropdown y prueba interactiva de preview. Bootstrap y Chart.js se ejecutan con sus versiones existentes; los gráficos se comprueban como instancias reales. El resto de realtime se valida con los tests separados, sin conectarse a producción.

## Límites y revisión manual para Víctor

1. Revisar este commit local y las capturas antes de autorizar push/integración/despliegue.
2. Probar Configuración con una cuenta de cada rol, elegir una paleta, guardar, cerrar sesión y volver a entrar.
3. Revisar mensajes y pedidos con datos representativos en un entorno de pruebas; los datos de las capturas son sintéticos.
4. Comprobar la preferencia del sistema de movimiento reducido y la animación del login en un teléfono real.
5. Tras un futuro despliegue autorizado, cerrar/reabrir las ventanas de la PWA para activar el service worker nuevo. No se cachean páginas privadas.

Las preferencias históricas azul/verde/rojo/etc. se muestran como Gold Classic hasta que el usuario elija una de las cuatro paletas. No se hizo una auditoría visual exhaustiva de todas las pantallas secundarias ni de dispositivos físicos. La vista previa sin guardar se pierde al abandonar Configuración, intencionalmente.

No hubo push, merge, deploy, acceso a Railway/producción, ejecución de migraciones, cambios de credenciales ni borrado de datos. Analytics, modelos, las migraciones y la lógica de stock, pedidos, cobertura y notificaciones no se modificaron.
