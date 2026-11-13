# ADR-023: Un solo recordatorio a la empresa con más de 5 postulados sin revisar

- **Status:** Accepted
- **Date:** 2026-11-13
- **Decider:** Ilyra Rivas
- **Tags:** panel, correo, plan-gratis, hr-engine

## Context

Hoy la empresa se entera de que tiene postulados solo si entra al panel. Ningún correo
le llega a ella ni al candidato. Antes del lanzamiento en LinkedIn se planeó avisarle
de las postulaciones (el "PR 4").

Resend gratis da 100 correos al día. Los comparte con los códigos de acceso de Auth:
el de alta y el de cada entrada al panel. Si un código no llega, la empresa no entra.
Por eso la web dejó de mandar correos el 2026-11-13 y la moderación pasó a un resumen
al día.

Ilyra pidió el aviso así: "solo cuando ya tengan más de 5 postulados a sus ofertas y
que llegue un aviso cuando realmente se necesite avisarle a la persona si no ha
revisado el panel y recordarle los postulados". Y eligió esperar 24 horas.

## Decision

1. **Qué cuenta como sin revisar.** Una postulación a una vacante abierta que llegó
   después de la última vez que la empresa abrió las postulaciones de esa vacante, y
   después de su último recordatorio. Se suman todas las vacantes de la empresa.
2. **Cuándo se ve.** Al abrir "Ver postulaciones", el panel llama a
   `marcar_postulaciones_vistas(vacante)` (migración 0020). La RPC es
   `security definer`: la empresa sale del JWT, solo HR y Dirección marcan, y con la
   vacante de otra empresa no se marca nada. La fecha se guarda por vacante en
   `privado.postulaciones_vistas`, porque las postulaciones se abren por vacante.
3. **Cuándo sale.** Con más de 5 sin revisar, 24 horas después de que llegó el sexto,
   si la empresa sigue sin entrar. La regla es pura y vive en
   `app/domain/recordatorios.py` (`toca_recordar`).
4. **Uno solo.** Después de un recordatorio no sale otro hasta que la empresa abra sus
   postulaciones y se junten otros más de 5. Cada envío queda en
   `privado.recordatorios_de_postulados`.
5. **A quién.** A HR y Dirección de la empresa con el correo confirmado en Auth, que
   son quienes ven las postulaciones. Nunca al candidato.
6. **Qué dice.** Cuántos postulados hay, en qué vacantes y el enlace al panel. Ningún
   nombre ni dato de candidatos.
7. **Tope diario.** `RECORDATORIO_MAX_24H` (20 correos por defecto) cuenta correos, no
   empresas. Si una empresa no cabe, espera a la hora siguiente. Con 0, el recordatorio
   se apaga.
8. **Cada hora.** `postulados.recordar` con Celery beat, como las demás tareas, con
   `name=` explícito.

## Consequences

**Positivas:**
- La empresa que no vuelve al panel se entera de sus postulados sin que cada
  postulación gaste un correo.
- Los códigos de acceso conservan como mínimo 79 de los 100 correos del día: 20 de
  recordatorios y 1 de moderación.
- La regla de tenant vive en la base. El panel no puede marcar vacantes ajenas ni leer
  las tablas de `privado`.

**Negativas:**
- Si la empresa abre las postulaciones de una vacante y no las de otra, lo viejo de la
  otra ya no vuelve a recordarse: después de un recordatorio solo cuenta lo nuevo.
- El cockpit del plan con IA no marca nada. Solo cuenta abrir "Ver postulaciones".
- Si el SMTP falla con una de varias personas de la empresa, esa persona no lo recibe:
  basta con que una lo reciba para no repetirlo.

**Neutras:**
- Ninguna de las dos tablas nuevas guarda datos de candidatos.

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Un correo por postulación | Una vacante con 80 postulaciones agota la cuota de los códigos. Ilyra lo descartó. |
| La última entrada al panel (`last_sign_in_at`) como "ya los vio" | La sesión dura días: entrar no es revisar, y abrir el panel sin ver postulaciones apagaría el aviso. |
| Lo visto por empresa, no por vacante | El panel abre las postulaciones por vacante. Por empresa, ver una vacante borraría lo pendiente de otra. |
| Repetir el recordatorio cada 24 horas | Ilyra pidió uno solo hasta que la persona entre. |

## Fuentes

- Celery 5.6, Periodic Tasks: "schedule: The frequency of execution. This can be the
  number of seconds as an integer, a timedelta, or a crontab", y "You have to ensure
  only a single scheduler is running for a schedule at a time":
  https://docs.celeryq.dev/en/v5.6.3/userguide/periodic-tasks.html
- Postgres 17, INSERT: "ON CONFLICT DO UPDATE updates the existing row that conflicts
  with the row proposed for insertion": https://www.postgresql.org/docs/17/sql-insert.html
- Postgres 17, PL/pgSQL: `GET DIAGNOSTICS … ROW_COUNT`, "the number of rows processed
  by the most recent SQL command": https://www.postgresql.org/docs/17/plpgsql-statements.html
- Postgres 17, Window Functions: `row_number()` "Returns the number of the current row
  within its partition, counting from 1":
  https://www.postgresql.org/docs/17/functions-window.html
