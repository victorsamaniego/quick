# REV3: activación futura y rollback — REQUIERE VALIDACIÓN MANUAL

Este documento no autoriza despliegue ni ejecución de SQL. Los archivos 003 y 004
están preparados y **NO fueron ejecutados**. Las pruebas automáticas usan SQLite
en memoria; no demuestran la semántica concurrente de PostgreSQL.

## Estado y dependencias

- `SECURITY_SESSION_REVOCATION=true`: identidad de login HMAC derivada de usuario,
  hash vigente de contraseña y SECRET_KEY. No requiere migración. Invalida las
  sesiones y remember cookies anteriores al activar; requiere volver a iniciar
  sesión. Cambiar/resetear contraseña invalida cookies existentes en la siguiente
  carga de identidad. Los sockets pierden autorización para recibir y solicitar
  datos. No se cambia la contraseña ni SECRET_KEY para activar este control.
- `SECURITY_TOKEN_RECOVERY=true`: requiere revocación activa y tabla
  `password_reset_tokens` de 003. Token aleatorio de 256 bits, hash SHA-256 en DB,
  vida de 15 minutos, uso único, invalidación por reemisión/cambio de contraseña.
  La respuesta pública no confirma si existe la cuenta. En este modo las preguntas
  legacy no permiten completar recovery. Los resets administrativos solicitan
  email; no cambian la contraseña antes de consumir el token.
- `SECURITY_DELIVERY_CANDIDATES=true`: requiere tabla/índice de 004. Registra
  destinatarios del despacho, rechazo individual y ganador único. El pedido se
  bloquea antes que solicitud y candidato. Los eventos se emiten tras commit.
- Los tres flags están desactivados por defecto para no requerir un esquema nuevo
  al iniciar una instalación existente. Con flags desactivados siguen presentes
  las limitaciones del recovery, revocación y rechazo legacy. No confundir código
  implementado con protección activa en una instalación.
- No se añadieron dependencias para estos tres controles: SMTP usa biblioteca
  estándar. `user_security_state`, TOTP y recovery codes en 003 son preparación
  reservada y no tienen consumidores operativos. No declarar 2FA habilitado.

## Orden futuro, exclusivamente por operador autorizado

1. Revisar diff, baseline y reporte. Disponer de backup restaurable probado y un
   PostgreSQL desechable sin datos ni credenciales reales. Confirmar tipos y FK
   de `users`, `orders`, `delivery_requests`; detectar tablas de borradores anteriores.
2. Revisar y ensayar `migrations/003_rev3_auth_prepared.sql` en esa base aislada.
   Repetirlo y verificar esquema, índices, expiración, rollback transaccional y
   carreras entre consumo/consumo, reemisión/consumo y cambio de contraseña/consumo.
   `IF NOT EXISTS` no transforma tablas de un borrador incompatible: detenerse
   ante diferencias, sin DROP ni cambios de datos automáticos.
3. Revisar y ensayar `migrations/004_rev3_delivery_candidates_prepared.sql`, también
   dos veces. Es independiente de 003; exige `approximate_distance_km` y el índice
   parcial de un ganador. Probar con dos conexiones aceptación simultánea del
   mismo pedido, creación simultánea y expiración/aceptación. Comprobar un ganador,
   ninguna asignación pisada y ningún evento emitido antes del commit.
4. Solo después de esas validaciones, planificar aplicación manual del esquema
   aprobado antes de activar consumidores. Este trabajo no ejecutó ese paso.
5. En staging, configurar `PUBLIC_BASE_URL` como origen HTTPS explícito y
   `TRUSTED_HOSTS` verificados. Configurar fuera del repositorio `RESET_SMTP_HOST`,
   `RESET_SMTP_PORT` (465 TLS implícito o puerto STARTTLS), `RESET_SMTP_USERNAME`,
   `RESET_SMTP_PASSWORD`, `RESET_MAIL_FROM`. No copiar valores al reporte/logs.
   La verificación TLS es obligatoria y no hay fallback a SMTP plano.
6. Activar revocación en **todos** los workers de staging y reiniciarlos juntos;
   no mezclar versiones/modos. Avisar que todas las sesiones previas deben iniciar
   sesión otra vez. Comprobar los cuatro roles, remember, cambio y reset.
7. Activar recovery en todos los workers; probar entrega con buzones de staging,
   enlace HTTPS con fragmento, navegador con JS, token expirado/usado/reemitido,
   CSRF, no enumeración y fallo SMTP. Desactivar cualquier registro de bodies de
   formularios y tracking de enlaces en proveedores. El token circula por email
   y POST, nunca debe registrarse. No hay token en query ni cookie de sesión.
8. Pausar creación de solicitudes delivery durante la transición, dejar expirar
   las pendientes legacy (normalmente dos minutos; comprobar todas), activar
   candidatos en todos los workers y reanudar. No inferir destinatarios históricos
   con GPS actual ni hacer backfill. Validar A rechaza/B acepta, dos aceptaciones,
   reintentos, candidato ajeno, dirección privada y destino cero.
9. Completar checklist funcional REV3 en navegador: registro, cuatro logins,
   checkout y medios de pago, mapas/destino, QuickGold/radio, inventario/precios,
   chat/soporte/reconexión, PWA/logout y acciones administrativas. Validar Docker
   Linux y configuración de proxy/limiter compartido antes de aprobar un despliegue.

## Rollback conservador, no ejecutado

- Preferir corrección hacia adelante. Conservar tablas, hashes, marcas de uso,
  solicitudes y asignaciones. No ejecutar DROP, TRUNCATE, backfill ni restauración
  automática de contraseñas/pedidos/stock.
- Recovery: si falla entrega, corregir SMTP/cola; preservar revocación. Desactivar
  el flag reabre las preguntas legacy: no es un rollback rutinario seguro. Si es
  imprescindible retirar el consumidor, bloquear temporalmente recovery/reset
  administrativo en el perímetro hasta una solución revisada. Tokens emitidos
  expiran, se invalidan al reemitir y no se convierten en contraseñas permanentes.
- Revocación: no apagar el flag para recuperar cookies antiguas. Eso podría
  resucitar sesiones legacy. Conservar el loader/HMAC aunque se reviertan otras
  funciones. Si se exige volver al código anterior, requiere invalidación global
  de sesiones/cookies planificada por operador; no se rotó SECRET_KEY aquí.
- Candidatos: pausar despacho y respuestas, dejar terminar/expirar solicitudes
  según su modo; nunca servir candidatos existentes con rechazo global legacy.
  Conservar el consumidor de lectura/asignados mientras se prepara corrección.
  Ningún rollback debe reasignar pedidos aceptados ni reenviar eventos históricos.
- Cambios previos (CSRF, stock, uploads, dependencias, SW y roles): conservar el
  plan por grupo del reporte REV3. Revertir solo hunks identificados y validados,
  nunca resetear este worktree o la rama funcional ni modificar historial Git.

## Límites operativos que deben aceptarse explícitamente

- Correo: cola en memoria acotada por proceso, best effort; un reinicio puede
  perder trabajos. El usuario puede reintentar; cooldown por cuenta de 60 segundos.
  No hay garantía de entrega ni bandeja de reintentos persistida. Un proveedor
  puede conservar enlaces de recuperación; revisar su política y logs.
- Notificaciones delivery: destinatario persistido significa seleccionado para
  notificación, no acuse de recibo. Si el socket falla, la lista autenticada permite
  recuperar solicitudes; no existe outbox durable de eventos.
- Los locks se diseñaron para PostgreSQL READ COMMITTED. La suite SQLite prueba
  lógica, constraints y rollback, no carreras entre procesos ni bloqueos reales.
- Rate limiting y socket memberships siguen requiriendo validación distribuida.
  Configuración y SECRET_KEY deben ser consistentes entre workers.
- La revocación depende del hash actual: no se debe restaurar un hash histórico,
  porque podría revalidar identidades anteriores. No hay revocación individual de
  dispositivos ni panel de sesiones. No se implementaron 2FA/fresh auth en este bloque.
