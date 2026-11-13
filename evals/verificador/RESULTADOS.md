# Verificador de vacantes: comparación de modelos

## Confirmación con el código de producción (2026-11-13 00:07 UTC)

El PR 3 pasó el prompt, el esquema y la configuración de Gemini al código de la
moderación (`app/infrastructure/verificador_gemini.py`, `app/domain/verificador.py`), y
esta prueba ahora los importa de ahí. Se volvió a correr solo el modelo elegido, con el
mismo set:

| Modelo | Recall alto | Sospechosas como bajo | Falsos positivos | Exactitud | Errores | Costo por vacante | Costo total | Latencia media |
|---|---|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` (`thinking_level=LOW`) | 100% | 0 | 0% | 100% | 0 | US$0.00040 | US$0.0160 | 1.0 s |

Igual que en la comparación de abajo: es el modelo que usa la moderación
(`MODERACION_MODELO`).

## Comparación (2026-11-12)

Corrida del 2026-11-12 22:06 UTC con `python -m app.cli.evals_verificador` (services/hr-engine). Set sintético `casos.yaml`: 40 vacantes inventadas de México y Venezuela (22 legítimas, 13 de riesgo alto y 5 de riesgo medio). Mismo prompt para todos (`instrucciones.md`), salida estructurada con el esquema del script y una sola pasada por modelo.

- Claude: `thinking` adaptativo, `effort: low`, `output_config.format`. Opus 5.5 y Sonnet 5.5 con `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`); Haiku 5.5 no tiene fallback del lado del servidor y su negativa cuenta como revisión manual.
- Gemini: `generate_content` con `response_json_schema`; 2.5 con `thinking_budget=0` (como el hr-engine hoy) y los 3.x con `thinking_level=LOW`.
- Los modelos de Claude están listos en el script pero apagados por defecto (`--con-claude`): hoy no hay créditos en la API de Anthropic.

Criterio: el más barato con recall de alto = 100%, ninguna sospechosa como bajo y falsos positivos ≤ 10%.

### Resultados

| Modelo | Recall alto | Sospechosas como bajo | Falsos positivos | Exactitud | Negativas | Errores | Costo por vacante | Costo total | Latencia media |
|---|---|---|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | — | 0 | — | — | 0 | 40 | US$0.00000 | US$0.0000 | — |
| `gemini-3.5-flash-lite` | 100% | 0 | 0% | 100% | 0 | 0 | US$0.00040 | US$0.0160 | 1.0 s |
| `gemini-3.8-flash` | 100% | 0 | 0% | 100% | 0 | 0 | US$0.00091 | US$0.0363 | 2.7 s |

Sin correr:
- `claude-haiku-5-5`: apagado: sin créditos en la API de Anthropic (se activa con --con-claude)
- `claude-sonnet-5-5`: apagado: sin créditos en la API de Anthropic (se activa con --con-claude)
- `claude-opus-5-5`: apagado: sin créditos en la API de Anthropic (se activa con --con-claude)

Gasto de la corrida: US$0.0523 (tope US$1.00).

### Recomendación

gemini-3.5-flash-lite: el más barato que detectó todas las de riesgo alto, no dejó pasar ninguna sospechosa como bajo y mandó a revisión el 0% de las legítimas.

### Fallos por modelo

#### `gemini-2.5-flash`

- `leg-almacen-turno-rotativo`: esperado bajo, obtuvo error (API 404). Señal: puesto operativo con prestaciones
- `leg-asesor-seguros`: esperado bajo, obtuvo error (API 404). Señal: venta de seguros con base, capacitación y cédula, sin cobro
- `leg-asistente-administrativa`: esperado bajo, obtuvo error (API 404). Señal: oferta administrativa estándar
- `leg-atencion-home-office`: esperado bajo, obtuvo error (API 404). Señal: home office legítimo con equipo propio y sueldo realista
- `leg-ayudante-construccion`: esperado bajo, obtuvo error (API 404). Señal: pago semanal en obra, legítimo
- `leg-backend-remoto`: esperado bajo, obtuvo error (API 404). Señal: trabajo remoto real con proceso técnico
- `leg-cajero-farmacia`: esperado bajo, obtuvo error (API 404). Señal: puesto de tienda estándar
- `leg-call-center-bilingue`: esperado bajo, obtuvo error (API 404). Señal: call center con sueldo y capacitación pagada
- `leg-celulares-whatsapp-y-tienda`: esperado bajo, obtuvo error (API 404). Señal: WhatsApp junto a tienda física y datos verificables
- `leg-chofer-vehiculo-empresa`: esperado bajo, obtuvo error (API 404). Señal: chofer con vehículo de la empresa
- `leg-cocinero-cancun`: esperado bajo, obtuvo error (API 404). Señal: hotelería con propinas
- `leg-contador-junior`: esperado bajo, obtuvo error (API 404). Señal: puesto profesional estándar
- `leg-disenador-freelance`: esperado bajo, obtuvo error (API 404). Señal: freelance por proyecto con contrato de servicios
- `leg-encuestador-pago-por-pieza`: esperado bajo, obtuvo error (API 404). Señal: pago por pieza legítimo de empresa de investigación
- `leg-enfermera-nocturno`: esperado bajo, obtuvo error (API 404). Señal: puesto clínico estándar
- `leg-pasantia-academica`: esperado bajo, obtuvo error (API 404). Señal: pasantía curricular sin pago, con convenio universitario
- `leg-profesor-ingles-online`: esperado bajo, obtuvo error (API 404). Señal: remoto con pago por hora razonable
- `leg-reclutador-junior`: esperado bajo, obtuvo error (API 404). Señal: comisión por colocación con base fija
- `leg-repartidor-moto-propia`: esperado bajo, obtuvo error (API 404). Señal: pide moto propia pero paga por entrega y reconoce gasolina
- `leg-tecnico-mantenimiento`: esperado bajo, obtuvo error (API 404). Señal: técnico industrial estándar
- `leg-vendedor-piso-comision`: esperado bajo, obtuvo error (API 404). Señal: comisión por ventas en tienda física
- `leg-ventas-b2b-comision`: esperado bajo, obtuvo error (API 404). Señal: comisiones con sueldo base y prestaciones
- `sos-cripto-inversion`: esperado alto, obtuvo error (API 404). Señal: inversión en cripto con promesa de duplicar
- `sos-datos-bancarios-antes`: esperado alto, obtuvo error (API 404). Señal: datos bancarios e identificación antes de la entrevista
- `sos-deposito-capacitacion`: esperado alto, obtuvo error (API 404). Señal: depósito para apartar lugar
- `sos-enlace-acortado`: esperado medio, obtuvo error (API 404). Señal: enlace acortado y sin datos de la empresa
- `sos-ensobretado-material`: esperado alto, obtuvo error (API 404). Señal: cobro por material de trabajo desde casa
- `sos-examen-medico-clinica`: esperado alto, obtuvo error (API 404). Señal: cobro por examen médico en clínica indicada
- `sos-kit-de-inicio`: esperado alto, obtuvo error (API 404). Señal: cobro por kit de inicio (multinivel)
- `sos-likes-pagados-usdt`: esperado alto, obtuvo error (API 404). Señal: estafa de tareas (pagan por dar likes, en cripto)
- `sos-modelos-telegram`: esperado alto, obtuvo error (API 404). Señal: señales de trata (viaje pagado, fotos de cuerpo, contacto solo por Telegram)
- `sos-mula-de-dinero`: esperado alto, obtuvo error (API 404). Señal: mula de dinero (recibir y reenviar transferencias)
- `sos-paquetes-frontera`: esperado alto, obtuvo error (API 404). Señal: actividad ilegal disfrazada (traslado de paquetes sin saber contenido)
- `sos-se-tu-propio-jefe`: esperado medio, obtuvo error (API 404). Señal: «sé tu propio jefe» vago, sin empresa ni puesto
- `sos-solo-telegram-digitador`: esperado medio, obtuvo error (API 404). Señal: contacto solo por Telegram
- `sos-solo-whatsapp-sin-empresa`: esperado medio, obtuvo error (API 404). Señal: contacto solo por WhatsApp, sin empresa identificable
- `sos-sueldo-irreal-desde-casa`: esperado medio, obtuvo error (API 404). Señal: sueldo irreal + sin experiencia + desde casa, sin cobro explícito
- `sos-suplantacion-marca`: esperado alto, obtuvo error (API 404). Señal: suplanta a una marca conocida, cobra activación y usa enlace acortado
- `sos-tarjeta-y-cvv`: esperado alto, obtuvo error (API 404). Señal: pide datos de tarjeta y CVV
- `sos-trabajo-exterior-tramites`: esperado alto, obtuvo error (API 404). Señal: trabajo en el exterior con cobro por trámites (posible trata)


### Estimación antes de correr

| Modelo | Precio (entrada / salida por millón) | Estimado para el set | Fuente |
|---|---|---|---|
| `claude-haiku-5-5` | US$0.10 / US$0.50 | ~US$0.010 | skill claude-api, tabla Current Models (2026-11-03). |
| `claude-sonnet-5-5` | US$2.00 / US$10.00 | ~US$0.207 | skill claude-api, tabla Current Models (2026-11-03). |
| `claude-opus-5-5` | US$4.00 / US$20.00 | ~US$0.414 | skill claude-api, tabla Current Models (2026-11-03). |
| `gemini-2.5-flash` | US$0.30 / US$2.50 | ~US$0.043 | https://ai.google.dev/gemini-api/docs/pricing. el del hr-engine hoy; deprecado, desde el 2026-12-01 se redirige a 3.5 Flash-Lite. |
| `gemini-3.5-flash-lite` | US$0.30 / US$2.50 | ~US$0.043 | https://ai.google.dev/gemini-api/docs/pricing. el Flash-Lite vigente y el reemplazo oficial de 2.5 Flash. |
| `gemini-3.8-flash` | US$0.75 / US$3.75 | ~US$0.078 | https://ai.google.dev/gemini-api/docs/pricing. el Flash más nuevo; sube a US$1,50 / US$7,50 desde el 2027-01-01. |
| `gemini-2.5-flash-lite` | US$0.10 / US$0.40 | ~US$0.009 | https://ai.google.dev/gemini-api/docs/pricing. no deprecado, pero la API solo lo da a quien ya lo usaba; solo con --modelos. |
