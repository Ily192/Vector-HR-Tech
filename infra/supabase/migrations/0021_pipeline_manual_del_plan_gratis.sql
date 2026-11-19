-- ════════════════════════════════════════════════════════════════════════════
-- Fluve AI · 0021_pipeline_manual_del_plan_gratis
-- Fecha: 2026-11-19
-- El plan gratis usa todas las etapas del pipeline, a mano y sin IA (ADR-024).
-- Requiere: 0001..0020
-- ════════════════════════════════════════════════════════════════════════════
--
-- Ilyra, el 2026-11-19: "Las personas deben tener acceso a todos esos pasos,
-- ningún servicios IA. Desbloquea esos pasos… Por ahora lo único que monetiza
-- este panel es que la empresa desee publicar más de 3 vacantes".
--
--   · Se va el trigger de 0009 que devolvía PT403 al mover una aplicación del
--     plan gratis a evaluated, shortlisted, interviewed u offered. La empresa
--     mueve a sus candidatos entre todas las etapas y los cierra como
--     contratados, descartados o retirados. Lo hace con su sesión y solo en sus
--     aplicaciones: eso lo siguen cuidando la policy `applications_tenant_write`
--     (0004: solo HR y Dirección de la empresa del JWT) y las FK compuestas, que
--     no dejan colgar una aplicación de la vacante o el candidato de otra empresa.
--   · Cambiar de etapa no toca nada de lo que ADR-019 protege (lo prueban
--     `tests/security/test_pipeline_manual.py` y `test_evaluaciones_ia.py`):
--       - el tope de 50 cuenta las recibidas (`privado.aplicaciones_recibidas`,
--         0010): mover, descartar o borrar no libera cupo;
--       - la oposición del candidato (`sin_ia`) no la retira la empresa (0010);
--       - entrevistas, psicométricos y constancias siguen siendo del plan con IA
--         (0010): la etapa "En entrevista" no crea una entrevista;
--       - ninguna etapa enciende la IA: el barrido de evaluación solo toma
--         aplicaciones de empresas `ia` que siguen en "Aplicados" (ADR-021).
--     Y mover a alguien no manda ningún correo.
--   · El cambio de etapa deja en orden la fecha y el motivo. Reemplaza al
--     trigger de 0015 sin cambiar su regla:
--       - lo que evaluó la IA no se descarta sin motivo (PT422, ADR-021 §4); sin
--         score el motivo es opcional, de 10 a 500 caracteres si se escribe;
--       - al cerrar (contratado, descartado o retirado) se fija `decided_at`;
--       - al volver a una etapa del pipeline se borra `decided_at`;
--       - el motivo del descarte se borra en cuanto la aplicación deja de estar
--         descartada: es un dato del candidato que ya no aplica.
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- ─── 1. Todas las etapas para los dos planes ────────────────────────────────

drop trigger if exists applications_etapas_del_plan on public.applications;
drop function if exists public.applications_respeta_etapas_del_plan();

comment on column public.applications.status is
    'Etapa de la aplicación. La mueve una persona de la empresa, en los dos planes (ADR-024). La IA del plan de pago solo pasa de applied a evaluated lo que evalúa (ADR-021).';

-- ─── 2. La fecha y el motivo al cambiar de etapa ────────────────────────────
--
-- Sin `security definer`: solo mira la fila que cambia. También en el insert,
-- para que una aplicación que la empresa da de alta ya cerrada lleve su fecha.

drop trigger if exists applications_descarte_con_motivo on public.applications;
drop function if exists public.applications_descarte_con_motivo();

create or replace function public.applications_al_cambiar_de_etapa()
    returns trigger
    language plpgsql
    set search_path = ''
as $$
begin
    if tg_op = 'UPDATE' and new.status = old.status then
        return new;
    end if;

    if new.status = 'rejected'
       and new.fit_score is not null
       and coalesce(btrim(new.motivo_de_descarte), '') = '' then
        raise exception 'descartar una aplicación evaluada con IA exige un motivo'
            using errcode = 'PT422',
                  hint = 'La IA solo sugiere: una persona decide y deja el motivo (ADR-021).';
    end if;

    if new.status in ('hired', 'rejected', 'withdrawn') then
        -- Vector HR (sin sesión de tenant) puede fijar otra; si nadie la fija, es ahora.
        if (tg_op = 'INSERT' and new.decided_at is null)
           or (tg_op = 'UPDATE' and new.decided_at is not distinct from old.decided_at) then
            new.decided_at := now();
        end if;
    else
        new.decided_at := null;
    end if;

    if new.status <> 'rejected' then
        new.motivo_de_descarte := null;
    end if;
    return new;
end;
$$;

revoke execute on function public.applications_al_cambiar_de_etapa() from public, anon, authenticated;

create trigger applications_al_cambiar_de_etapa
    before insert or update of status on public.applications
    for each row execute function public.applications_al_cambiar_de_etapa();

comment on column public.applications.motivo_de_descarte is
    'Por qué una persona descartó la aplicación. Obligatorio si la evaluó la IA (ADR-021 §4); si no, opcional. Se borra si la aplicación sale de descartados (ADR-024).';

commit;
