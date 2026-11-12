-- ════════════════════════════════════════════════════════════════════════════
-- Vortex Ops · 0018_altas_desde_la_web
-- Fecha: 2026-11-12
-- Los registros de vectorhrtech.com/publicar-vacantes que dan de alta una empresa.
-- Requiere: 0001..0017
-- ════════════════════════════════════════════════════════════════════════════
--
-- La web guarda el lead en su base y llama al hr-engine (`POST /alta/plan-gratis`).
-- El hr-engine crea la empresa y la cuenta, y Auth manda un código de 6 dígitos
-- que la persona escribe en el panel (enmienda del 2026-11-12 a ADR-017).
--
-- Esta tabla sirve para tres cosas:
--   · Idempotencia: `lead_id` es único; un reintento de la web no crea otra empresa.
--   · Verificación (PR 2): el sitio web, el LinkedIn y el cargo que dio la empresa.
--   · Limpieza: las empresas cuyo dueño no escribió el código en 7 días se borran
--     (tarea diaria del hr-engine); `confirmado_en` dice quién sí lo hizo.
--
-- La IP no se guarda: solo su HMAC (`ip_hash`), para los topes y para ver ráfagas.
-- Vive en `privado`, que el Data API no publica; solo la toca el hr-engine con el
-- rol dueño. Nada de candidatos.
-- ════════════════════════════════════════════════════════════════════════════

begin;

create table if not exists privado.altas_web (
    id bigint generated always as identity primary key,
    lead_id text not null unique check (length(lead_id) between 1 and 64),
    empresa_id uuid references public.empresas (id) on delete cascade,
    correo text not null,
    -- NULL mientras el alta está en curso; si falla, la fila se borra.
    resultado text check (resultado in ('empresa_creada', 'cuenta_existente')),
    publica_para text not null check (publica_para in ('propia', 'clientes')),
    cargo text,
    web_empresa text,
    linkedin text,
    verificacion text not null check (verificacion in ('dominio', 'revision')),
    pais text not null check (pais in ('mx', 've', 'otro')),
    tamano text check (tamano in ('1-15', '16-50', '51-200', '200+')),
    sector text not null,
    contrataciones_mes text not null,
    puestos text[] not null default '{}',
    origen text,
    utm_medium text,
    utm_campaign text,
    ip_hash text,
    creado_en timestamptz not null default now(),
    confirmado_en timestamptz
);

create index if not exists altas_web_empresa_idx on privado.altas_web (empresa_id);
-- La limpieza diaria busca las que nadie confirmó.
create index if not exists altas_web_sin_confirmar_idx on privado.altas_web (creado_en)
    where confirmado_en is null and resultado = 'empresa_creada';

alter table privado.altas_web enable row level security;
revoke all on privado.altas_web from public, anon, authenticated;

commit;
