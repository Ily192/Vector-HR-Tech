# ADR-017: El career site es el módulo gratuito de Vortex, no un sitio de marketing

- **Status:** Proposed
- **Date:** 2026-10-16
- **Decider:** Ilyra
- **Tags:** producto, career-site, hrbp, multi-tenant

## Context

Hoy el career-site mezcla dos públicos con objetivos distintos:

- **Candidatos**, que buscan una vacante y quieren aplicar.
- **Empresas**, a las que les pide "Agendar demo" y "Hablar con Vector HR" desde
  la cabecera, el hero, el cierre y la página `/contacto`.

El modelo de negocio es otro. Una empresa llega al career site **porque ya
contactó a Vector HR**. A cambio de su registro, publica vacantes gratis en el
career site de Vortex. Pedirle una demo en un sitio al que ya tiene acceso no
tiene sentido. Y a un candidato, ese mensaje no le sirve.

Además, `hrbp` está pensado como el cockpit de un cliente que ya paga los
servicios de IA. No tiene un lugar para la empresa que solo publica.

## Decision

1. **Vortex es una sola aplicación para empresas, organizada en módulos.**
   - **Career site** (gratis): crear empleo, ver sus vacantes y las aplicaciones
     que reciben, y editar el perfil de empresa. Es el **único módulo gratuito**.
   - **Servicios de IA** (de pago): cockpit del día, evaluación a ciegas,
     búsqueda de perfiles, agentes y reportes.
   - El código vive en `apps/hrbp`, que pasa a ser la app de la empresa. El
     nombre del paquete se puede cambiar más adelante.
2. **No hay registro abierto.** La cuenta de una empresa la crea Vector HR
   cuando la empresa la contacta (alta asistida). Ese registro es la
   contraprestación del plan gratuito.
3. **El career site público es solo para candidatos** ("Vortex Empleos"):
   - muestra las vacantes de todas las empresas con plan activo, con filtros,
     salario visible cuando la empresa lo da, y la aplicación;
   - no tiene CTAs de venta a empresas;
   - el único enlace para empresas es "¿Publicas vacantes? Entra a tu panel".
4. **La única venta indirecta está en "Crear empleo"**:
   - un brochure breve de los servicios, ligado al momento: "cuando lleguen las
     aplicaciones, Vector HR puede leerlas por ti";
   - se puede ocultar;
   - tiene un solo CTA ("Quiero saber más"), que avisa al contacto de Vector HR
     de esa empresa. No lleva a una agenda ni a una tabla de precios.
   - Los módulos de pago **no aparecen** en el menú de una empresa gratuita: no
     hay candados.
5. **La venta a empresas que todavía no conocen Vector HR** (landing, demo,
   contacto) **sale del career site**. Se queda en la web de Vector HR, y la demo
   NOM-035 sigue siendo el gancho de captación.
6. **El plan lo decide el backend.** El plan de la empresa y los módulos que
   tiene viajan en `app_metadata`, igual que el tenant (ADR-015). RLS los
   respeta. La UI solo lee `modulos` de la sesión para pintar el menú (ADR-016).

## Consequences

**Positivas:**

- Cada público recibe un mensaje único: el candidato, vacantes; la empresa,
  su panel.
- El gratuito es el paso **anterior** al producto (publicar y recibir
  aplicaciones), no una versión recortada del producto (evaluar). No canibaliza
  los servicios de IA, y genera la necesidad de leer muchos CVs.
- Las aplicaciones llegan dentro de Vortex. Activar la evaluación a ciegas es
  cambiar de plan, no migrar datos.

**Negativas / trabajo que implica:**

- `vacantes_publicas` tiene que exponer el nombre y el slug de la empresa,
  nunca su `empresa_id`. Hace falta una migración.
- Hay que modelar el plan y los módulos (`empresas.plan` o una tabla de
  módulos) y propagarlos al JWT en el hook de ADR-015.
- La home, `/contacto`, la cabecera y los tests del career-site que hoy fijan
  el texto comercial se reescriben, junto con el smoke E2E.
- Hace falta un canal interno para el "Quiero saber más": `activity_log` más un
  aviso a Vector HR.

**Neutras:**

- El dominio y el hosting no cambian. La web comercial de Vector HR puede vivir
  fuera de este repo.

## Preguntas abiertas (las decide Ilyra antes de pasar a Accepted)

1. ¿El plan gratuito tiene **límite de vacantes activas**, o es sin límite?
2. ¿La empresa gratuita **ve y gestiona las aplicaciones** que recibe (lista,
   CV, cambiar estado), o solo las recibe por correo?
3. ¿El career site es **uno solo para todas las empresas**, o cada empresa
   tiene además su página propia (`/empresas/<slug>`)? El mockup D asume las
   dos cosas.
4. ¿Quién da de alta a la empresa: Vector HR a mano, o una invitación que
   Vector HR envía y la empresa completa?

## Alternatives considered

| Alternativa | Por qué descartada |
|---|---|
| Mantener el career site como landing de venta con vacantes | Mezcla públicos y contradice el modelo: la empresa ya es cliente gratuito. |
| Prueba gratuita de los servicios de IA en lugar de career site gratis | Regala el producto en vez del paso previo; enseña a usarlo sin pagar. |
| Mostrar los módulos de pago con candado a la empresa gratuita | Más presión comercial en todo el panel; Ilyra quiere un único punto de venta indirecta. |
