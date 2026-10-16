import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Wordmark,
} from "@vortex/ui";
import { ArrowRight, Check, Shield, Sparkles, Zap } from "lucide-react";
import Link from "next/link";

const PILARES = [
  {
    icon: Zap,
    burbuja: "bg-flame-50 text-flame-700",
    titulo: "Velocidad",
    descripcion: "Agentes autónomos que procesan candidatos en minutos, no semanas.",
    puntos: ["Sourcing 24/7", "Scoring vectorial + AI", "Onboarding automatizado"],
  },
  {
    icon: Sparkles,
    burbuja: "bg-aqua-50 text-aqua-700",
    titulo: "Inteligencia",
    descripcion: "LLMs orquestados con governance, no prompts sueltos.",
    puntos: [
      "Skills versionadas con evals",
      "Multi-modelo (OpenAI + Gemini + Claude)",
      "Costo de cada run registrado",
    ],
  },
  {
    icon: Shield,
    burbuja: "bg-ink-50 text-ink-700",
    titulo: "Control",
    descripcion: "Multi-tenant, self-hostable, audit log en cada paso.",
    puntos: ["RLS Postgres nativo", "Run-tokens JWT 5 min", "LGPD / Habeas Data ready"],
  },
] as const;

/** Vista previa del producto: lo que ve un HRBP cuando un agente evalúa a alguien. */
function VistaPrevia() {
  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-md">
      <div className="absolute -inset-6 -z-10 rounded-[40px] bg-[radial-gradient(60%_60%_at_70%_20%,rgb(62_236_235/0.25),transparent),radial-gradient(50%_50%_at_20%_90%,rgb(254_120_2/0.18),transparent)] blur-2xl" />
      <div className="rounded-[28px] bg-ink-900 p-5 text-white shadow-float">
        <div className="mb-5 flex items-center justify-between">
          <Wordmark brand="vortex" size="sm" tone="dark" withMark />
          <span className="inline-flex items-center gap-1.5 rounded-full bg-aqua-300/15 px-2.5 py-1 text-xs font-bold text-aqua-300">
            <span className="h-1.5 w-1.5 rounded-full bg-aqua-300" /> En vivo
          </span>
        </div>
        <div className="space-y-3">
          <div className="rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/10">
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-aqua-300">
              Agente cv-evaluator · hace 2 min
            </p>
            <p className="mt-2 text-[15px] font-bold">Backend Engineer · candidata #482</p>
            <div className="mt-3 flex items-center gap-3">
              <span className="text-3xl font-extrabold tracking-tight">8.5</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                <div className="h-full w-[85%] rounded-full bg-brand-gradient" />
              </div>
            </div>
            <p className="mt-3 text-sm text-mist-300">
              Encaja en Python y FastAPI; le falta experiencia con Celery.
            </p>
          </div>
          <div className="flex items-center justify-between rounded-2xl bg-white/[0.06] px-4 py-3 ring-1 ring-white/10">
            <span className="text-sm text-mist-300">Siguiente paso</span>
            <span className="rounded-full bg-flame-500 px-3 py-1 text-xs font-bold text-ink-900">
              Entrevista
            </span>
          </div>
          <div className="flex items-center gap-2 px-1 text-xs text-mist-300">
            <Check className="h-3.5 w-3.5 text-aqua-300" /> Evaluación a ciegas: el modelo no ve el
            nombre
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="container mx-auto grid items-center gap-14 px-4 py-16 md:px-6 md:py-24 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div>
            <Badge variant="ai" className="mb-6">
              <Sparkles className="h-3 w-3" />
              Powered by agentic AI
            </Badge>
            <h1 className="mb-6 text-[clamp(2.4rem,5.2vw,4rem)] font-extrabold leading-[1.04] tracking-[-0.035em]">
              Hackeando la rutina, <span className="brand-underline">liberando el talento</span>
            </h1>
            <p className="mb-10 max-w-xl text-lg text-muted-foreground md:text-xl">
              El Operations Engine agentic que ejecuta tus procesos de HR, Sales y operaciones
              end-to-end. Multi-canal, multi-tenant, self-hostable.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button size="lg" asChild>
                <Link href="/vacantes">
                  Ver vacantes abiertas
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="secondary" asChild>
                <Link href="/contacto">Hablar con Vector HR</Link>
              </Button>
            </div>
          </div>
          <VistaPrevia />
        </div>
      </section>

      {/* Pilares */}
      <section className="container mx-auto px-4 pb-20 md:px-6">
        <div className="mb-10 max-w-2xl">
          <span className="eyebrow">Una sola plataforma</span>
          <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.03em] md:text-4xl">
            Tres pilares, una sola plataforma
          </h2>
          <p className="mt-3 text-muted-foreground">
            Autoridad, rebeldía y jovialidad — sin la rigidez del HR tech tradicional.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {PILARES.map((p) => (
            <Card key={p.titulo} data-pilar={p.titulo}>
              <CardHeader>
                <span className={`mb-3 grid h-11 w-11 place-items-center rounded-xl ${p.burbuja}`}>
                  <p.icon className="h-5 w-5" />
                </span>
                <CardTitle>{p.titulo}</CardTitle>
                <CardDescription className="text-[15px]">{p.descripcion}</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2.5 text-sm text-mist-700">
                  {p.puntos.map((punto) => (
                    <li key={punto} className="flex items-start gap-2.5">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-aqua-600" />
                      {punto}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Cierre */}
      <section className="container mx-auto px-4 pb-20 md:px-6">
        <div className="on-ink relative overflow-hidden rounded-[28px] bg-ink-900 px-6 py-10 text-white md:px-12 md:py-14">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_300px_at_100%_0%,rgb(62_236_235/0.22),transparent_60%),radial-gradient(500px_280px_at_0%_100%,rgb(254_120_2/0.22),transparent_60%)]" />
          <div className="relative grid items-center gap-8 md:grid-cols-[minmax(0,1fr)_auto]">
            <div>
              <span className="eyebrow">Demo de 20 minutos</span>
              <h2 className="mt-3 text-3xl font-extrabold tracking-[-0.03em] md:text-4xl">
                ¿Qué proceso te está comiendo el tiempo?
              </h2>
              <p className="mt-3 max-w-xl text-[#C9CCF2]">
                Te mostramos cómo los agentes de Vortex Ops lo ejecutan de punta a punta, con tus
                datos de ejemplo y tu vocabulario.
              </p>
            </div>
            <Button size="lg" asChild>
              <Link href="/contacto">
                Agendar una demo <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}
