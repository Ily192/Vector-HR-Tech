-- Seed para desarrollo local. NO correr en producción.
-- IDs deterministas para que tests y fixtures puedan referenciarlos.

-- ─── empresas ───────────────────────────────────────────────────────────────
insert into empresas (id, name, slug, color_primario)
values
    ('11111111-1111-1111-1111-111111111111', 'Vector HR Tech', 'vector-hr', '#1E1B4B'),
    ('22222222-2222-2222-2222-222222222222', 'Siete', 'siete', '#FF7F00')
on conflict (slug) do nothing;

-- ─── vacantes ───────────────────────────────────────────────────────────────
insert into vacantes (id, empresa_id, slug, title, jd, modality, status, seniority)
values
    (
        'aaaaaaaa-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111',
        'senior-software-engineer',
        'Senior Software Engineer',
        'Liderar arquitectura de servicios Python/FastAPI multi-tenant.',
        'remote',
        'open',
        'senior'
    ),
    (
        'aaaaaaaa-0000-0000-0000-000000000002',
        '11111111-1111-1111-1111-111111111111',
        'hr-business-partner',
        'HR Business Partner',
        'Acompañar líderes técnicos en ciclos de talento end-to-end.',
        'hybrid',
        'open',
        'semi-senior'
    ),
    (
        'bbbbbbbb-0000-0000-0000-000000000001',
        '22222222-2222-2222-2222-222222222222',
        'reclutador-it',
        'Reclutador IT',
        'Búsqueda activa de talento tech para clientes LATAM.',
        'remote',
        'open',
        'junior'
    )
on conflict (empresa_id, slug) do nothing;

-- ─── candidatos ─────────────────────────────────────────────────────────────
insert into candidatos (id, empresa_id, full_name, email, headline, source)
values
    (
        'cccccccc-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111',
        'Ada Lovelace',
        'ada@example.test',
        'Software architect · async Python',
        'career-site'
    ),
    (
        'cccccccc-0000-0000-0000-000000000002',
        '11111111-1111-1111-1111-111111111111',
        'Linus Torvalds',
        'linus@example.test',
        'Kernel hacker',
        'linkedin'
    ),
    (
        'dddddddd-0000-0000-0000-000000000001',
        '22222222-2222-2222-2222-222222222222',
        'Grace Hopper',
        'grace@example.test',
        'Compiler engineer',
        'manual'
    )
on conflict (empresa_id, email) do nothing;

-- ─── applications ───────────────────────────────────────────────────────────
insert into applications (id, empresa_id, vacante_id, candidato_id, status, fit_score)
values
    (
        'eeeeeeee-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111',
        'aaaaaaaa-0000-0000-0000-000000000001',
        'cccccccc-0000-0000-0000-000000000001',
        'evaluated',
        8.5
    ),
    (
        'eeeeeeee-0000-0000-0000-000000000002',
        '11111111-1111-1111-1111-111111111111',
        'aaaaaaaa-0000-0000-0000-000000000001',
        'cccccccc-0000-0000-0000-000000000002',
        'applied',
        null
    ),
    (
        'ffffffff-0000-0000-0000-000000000001',
        '22222222-2222-2222-2222-222222222222',
        'bbbbbbbb-0000-0000-0000-000000000001',
        'dddddddd-0000-0000-0000-000000000001',
        'shortlisted',
        9.2
    )
on conflict (vacante_id, candidato_id) do nothing;

-- ─── psicometricos ──────────────────────────────────────────────────────────
insert into psicometricos (id, empresa_id, application_id, token, status, expires_at)
values
    (
        '99999999-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111',
        'eeeeeeee-0000-0000-0000-000000000001',
        'psy-tok-vec-001',
        'pending',
        now() + interval '7 days'
    ),
    (
        '99999999-0000-0000-0000-000000000002',
        '22222222-2222-2222-2222-222222222222',
        'ffffffff-0000-0000-0000-000000000001',
        'psy-tok-siete-001',
        'completed',
        now() + interval '7 days'
    )
on conflict do nothing;
