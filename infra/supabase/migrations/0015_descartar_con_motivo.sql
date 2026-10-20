-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0015_descartar_con_motivo
-- Fecha: 2026-10-21
-- Descartar lo que evaluó la IA exige una persona y un motivo (ADR-021 §4).
-- Requiere: 0001..0014
-- ════════════════════════════════════════════════════════════════════════════
--
-- La IA del plan de pago puntúa y sugiere un siguiente paso; no descarta a nadie.
-- Es una de las condiciones de ADR-018 para evaluar candidatos reales: "Descartar
-- exige una acción humana con motivo". La regla vive en la base, así que vale
-- también para cualquier vía que no sea el panel.
--
--   · `applications.motivo_de_descarte`: lo que escribe quien descarta, de 10 a
--     500 caracteres. Es un dato del candidato: se borra con la aplicación.
--   · Pasar a "descartado" una aplicación con score de la IA sin motivo devuelve
--     PT422 (PostgREST lo traduce a 422). Sin score no se pide: ahí no hubo IA.
--   · Al descartar se fija `decided_at`, si no lo tenía.
-- ════════════════════════════════════════════════════════════════════════════

begin;

alter table public.applications
    add column if not exists motivo_de_descarte text
        check (motivo_de_descarte is null
               or char_length(btrim(motivo_de_descarte)) between 10 and 500);

comment on column public.applications.motivo_de_descarte is
    'Por qué una persona descartó la aplicación. Obligatorio si la evaluó la IA (ADR-021 §4).';

create or replace function public.applications_descarte_con_motivo()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if new.status = 'rejected' and old.status is distinct from 'rejected' then
        if new.fit_score is not null and coalesce(btrim(new.motivo_de_descarte), '') = '' then
            raise exception 'descartar una aplicación evaluada con IA exige un motivo'
                using errcode = 'PT422',
                      hint = 'La IA solo sugiere: una persona decide y deja el motivo (ADR-021).';
        end if;
        new.decided_at := coalesce(new.decided_at, now());
    end if;
    return new;
end;
$$;

revoke execute on function public.applications_descarte_con_motivo() from public, anon, authenticated;

drop trigger if exists applications_descarte_con_motivo on public.applications;
create trigger applications_descarte_con_motivo
    before update of status on public.applications
    for each row execute function public.applications_descarte_con_motivo();

commit;
