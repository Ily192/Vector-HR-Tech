-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0016_resumen_del_cockpit
-- Fecha: 2026-10-20
-- El cockpit del plan con IA con datos reales (ADR-021, ADR-016 §4).
-- Requiere: 0001..0015
-- ════════════════════════════════════════════════════════════════════════════
--
-- El cockpit es el "hoy" de la empresa con IA y hasta aquí mostraba un ejemplo
-- fijo. `resumen_del_cockpit()` le da los números ya calculados, en una sola
-- llamada y solo de las vacantes abiertas de la empresa de la sesión:
--
--   · Candidatos en proceso y los que llegaron en 24 h; vacantes publicadas y
--     las de los últimos 7 días.
--   · Evaluaciones de la IA en 24 h y el % que terminó sin error (`runs`).
--   · Aplicaciones en espera del modelo y CVs evaluados en el mes contra el
--     tope de la empresa (`ia_cvs_por_mes`): la misma cuenta que usa el barrido.
--   · La decisión del día. Primero, quiénes están listos para entrevista: score
--     de la IA desde 7 y nadie los ha movido de "Evaluados". Después, lo que una
--     persona tiene que revisar a mano: sin evaluar tras 3 intentos, CV ilegible
--     o candidato que se opuso a la IA. Una decisión por vacante y tipo.
--   · La vacante del día (la de la decisión, o la de más candidatos en proceso),
--     con sus mejores evaluados y su embudo: cuántas aplicaciones llegaron a cada
--     etapa o más allá. Las descartadas solo cuentan en "Aplicados".
--   · El registro de los agentes de las últimas 24 h, sin nombres.
--
-- El costo en dólares no sale de aquí: es de Vector HR, no de la empresa
-- (`pricing-de-ia`). La empresa ve CVs evaluados contra su tope, que es lo que
-- la afecta: al llegar, lo nuevo espera al mes siguiente (ADR-021 §6).
--
-- Dos números son copias de reglas del hr-engine, y los tests de seguridad los
-- comparan con su dueña: 7 es `UMBRAL_ENTREVISTA` (`domain/siguiente_paso.py`,
-- `contracts/siguiente-paso.json`) y 3 es `MAX_INTENTOS` (`domain/evaluacion_ia.py`).
-- ════════════════════════════════════════════════════════════════════════════

begin;

-- Solo para empresas `ia` y para HR, Dirección o SuperAdmin de la empresa de la
-- sesión: a cualquier otro le devuelve cero filas.
create or replace function public.resumen_del_cockpit()
    returns table (
        candidatos_en_proceso int,
        candidatos_nuevos_24h int,
        vacantes_publicadas int,
        vacantes_nuevas_7d int,
        evaluaciones_24h int,
        -- Null si en 24 h no hubo evaluaciones.
        porcentaje_sin_error int,
        en_espera int,
        cvs_del_mes int,
        tope_del_mes int,
        porcentaje_del_tope int,
        tope_alcanzado boolean,
        decisiones_pendientes int,
        -- {tipo, vacante: {id, titulo}, listos, scores, sin_evaluar, ilegibles, sin_ia}
        decision jsonb,
        -- {id, titulo}; null si la empresa no tiene vacantes abiertas.
        vacante jsonb,
        evaluados int,
        -- [{id, candidato, score, razonamiento}], los 3 mejores de la vacante del día.
        mejores_evaluados jsonb,
        -- {applied, evaluated, shortlisted, interviewed, offered}
        embudo jsonb,
        -- [{id, en, agente, aplazada, vacante, score}], las 6 más recientes.
        registro jsonb
    )
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with empresa as (
        select e.id, e.ia_cvs_por_mes
          from public.empresas e
         where e.id = public.empresa_id()
           and public.app_role() in ('HR', 'Director', 'SuperAdmin')
           and e.plan = 'ia'
    ),
    abiertas as (
        select v.id, v.title, v.publicada_en
          from public.vacantes v
          join empresa on empresa.id = v.empresa_id
         where v.status = 'open'
    ),
    postulaciones as (
        select a.id, a.vacante_id, a.candidato_id, a.status, a.fit_score, a.fit_rationale,
               a.applied_at, a.sin_ia, c.full_name, c.cv_url,
               i.application_id is not null as ilegible,
               coalesce(ev.intentos, 0) as intentos,
               a.status in ('applied', 'evaluated', 'shortlisted', 'interviewed', 'offered')
                   as en_proceso
          from public.applications a
          join abiertas v on v.id = a.vacante_id
          left join public.candidatos c on c.id = a.candidato_id
          left join privado.cvs_ilegibles i on i.application_id = a.id
          left join privado.evaluaciones_ia ev on ev.application_id = a.id
    ),
    por_vacante as (
        select v.id, v.title, v.publicada_en,
               count(p.id) filter (where p.en_proceso) as en_proceso,
               count(p.id) filter (where p.status = 'evaluated' and p.fit_score >= 7) as listos,
               -- Lo que la IA no evaluó y nadie ha movido de "Aplicados".
               count(p.id) filter (
                   where p.status = 'applied' and p.fit_score is null and not p.sin_ia
                     and not p.ilegible and p.intentos >= 3
               ) as sin_evaluar,
               count(p.id) filter (
                   where p.status = 'applied' and p.fit_score is null and not p.sin_ia
                     and p.ilegible
               ) as ilegibles,
               count(p.id) filter (where p.status = 'applied' and p.sin_ia) as sin_ia
          from abiertas v
          left join postulaciones p on p.vacante_id = v.id
         group by v.id, v.title, v.publicada_en
    ),
    decisiones as (
        select id, title, publicada_en, 1 as prioridad, listos as cuantas, 'entrevistar' as tipo
          from por_vacante
         where listos > 0
        union all
        select id, title, publicada_en, 2, sin_evaluar + ilegibles + sin_ia, 'revisar'
          from por_vacante
         where sin_evaluar + ilegibles + sin_ia > 0
    ),
    decision as (
        select d.id, d.title, d.tipo
          from decisiones d
         order by d.prioridad, d.cuantas desc, d.publicada_en desc nulls last, d.id
         limit 1
    ),
    destacada as (
        select coalesce(
                   (select id from decision),
                   (select id from por_vacante
                     order by en_proceso desc, publicada_en desc nulls last, id
                     limit 1)
               ) as id
    ),
    corridas as (
        select r.id, r.agent_skill, r.status, r.started_at, r.payload
          from public.runs r
          join empresa on empresa.id = r.empresa_id
         where r.started_at >= now() - interval '24 hours'
    ),
    registro as (
        select r.id, r.started_at, r.agent_skill, r.status = 'failed' as aplazada,
               v.title as vacante, a.fit_score as score
          from corridas r
          -- El payload lo escribe el worker, pero se valida igual: un id mal formado
          -- no rompe el resumen y uno de otra empresa no se encuentra.
          left join public.applications a
                 on a.empresa_id = (select id from empresa)
                and a.id = case
                        when r.payload->>'application_id'
                             ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                        then (r.payload->>'application_id')::uuid
                    end
          left join public.vacantes v on v.id = a.vacante_id
         where r.status in ('completed', 'failed')
         order by r.started_at desc, r.id
         limit 6
    )
    select
        (select count(distinct candidato_id) from postulaciones where en_proceso)::int,
        (select count(distinct candidato_id) from postulaciones
          where applied_at >= now() - interval '24 hours')::int,
        (select count(*) from abiertas)::int,
        (select count(*) from abiertas where publicada_en >= now() - interval '7 days')::int,
        k.completadas,
        -- Hacia abajo: 100 % solo si no hubo ningún error.
        case when k.completadas + k.fallidas > 0
             then floor(100.0 * k.completadas / (k.completadas + k.fallidas))::int
        end,
        -- Las mismas que `resumen_de_evaluaciones().en_espera` (0014).
        (select count(*) from postulaciones
          where status = 'applied' and fit_score is null and not sin_ia
            and cv_url is not null and not ilegible and intentos < 3)::int,
        m.evaluados,
        empresa.ia_cvs_por_mes,
        case when empresa.ia_cvs_por_mes = 0 then 100
             else least(100, floor(100.0 * m.evaluados / empresa.ia_cvs_por_mes))::int
        end,
        m.evaluados >= empresa.ia_cvs_por_mes,
        (select count(*) from decisiones)::int,
        (select jsonb_build_object(
                    'tipo', d.tipo,
                    'vacante', jsonb_build_object('id', d.id, 'titulo', d.title),
                    'listos', pv.listos,
                    'scores', (select coalesce(jsonb_agg(s.fit_score order by s.fit_score desc),
                                               '[]'::jsonb)
                                 from (select p.fit_score from postulaciones p
                                        where p.vacante_id = d.id and p.status = 'evaluated'
                                          and p.fit_score >= 7
                                        order by p.fit_score desc
                                        limit 3) s),
                    'sin_evaluar', pv.sin_evaluar,
                    'ilegibles', pv.ilegibles,
                    'sin_ia', pv.sin_ia)
           from decision d
           join por_vacante pv on pv.id = d.id),
        (select jsonb_build_object('id', pv.id, 'titulo', pv.title)
           from por_vacante pv
          where pv.id = (select id from destacada)),
        (select count(*) from postulaciones
          where vacante_id = (select id from destacada) and en_proceso
            and fit_score is not null)::int,
        (select coalesce(jsonb_agg(jsonb_build_object('id', t.id,
                                                      'candidato', t.full_name,
                                                      'score', t.fit_score,
                                                      'razonamiento', t.fit_rationale)
                                   order by t.fit_score desc, t.applied_at, t.id),
                         '[]'::jsonb)
           from (select p.id, p.full_name, p.fit_score, p.fit_rationale, p.applied_at
                   from postulaciones p
                  where p.vacante_id = (select id from destacada)
                    and p.en_proceso and p.fit_score is not null
                  order by p.fit_score desc, p.applied_at, p.id
                  limit 3) t),
        (select jsonb_build_object(
                    'applied', count(*),
                    'evaluated', count(*) filter (
                        where status in ('evaluated', 'shortlisted', 'interviewed', 'offered',
                                         'hired')),
                    'shortlisted', count(*) filter (
                        where status in ('shortlisted', 'interviewed', 'offered', 'hired')),
                    'interviewed', count(*) filter (
                        where status in ('interviewed', 'offered', 'hired')),
                    'offered', count(*) filter (where status in ('offered', 'hired')))
           from postulaciones
          where vacante_id = (select id from destacada)),
        (select coalesce(jsonb_agg(jsonb_build_object('id', g.id,
                                                      'en', g.started_at,
                                                      'agente', g.agent_skill,
                                                      'aplazada', g.aplazada,
                                                      'vacante', g.vacante,
                                                      'score', g.score)
                                   order by g.started_at desc, g.id),
                         '[]'::jsonb)
           from registro g)
      from empresa
     cross join lateral (
        select (count(*) filter (where status = 'completed'))::int as completadas,
               (count(*) filter (where status = 'failed'))::int as fallidas
          from corridas
         where agent_skill = 'cv-evaluator'
     ) k
     cross join lateral (
        -- La cuenta del tope del barrido (0014): lo evaluado desde el día 1.
        select count(*)::int as evaluados
          from privado.evaluaciones_ia x
         where x.empresa_id = empresa.id
           and x.evaluada_en >= date_trunc('month', now())
     ) m;
$$;

revoke execute on function public.resumen_del_cockpit() from public, anon;
grant execute on function public.resumen_del_cockpit() to authenticated;

comment on function public.resumen_del_cockpit() is
    'El "hoy" del cockpit del plan con IA, ya calculado: indicadores, decisión del día, vacante del día y registro de los agentes (0016, ADR-021).';

commit;
