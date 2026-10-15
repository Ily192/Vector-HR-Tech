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
import { Activity, Briefcase, Users, Zap } from "lucide-react";

const KPIS = [
  {
    icon: Briefcase,
    burbuja: "bg-flame-500/15 text-flame-400",
    label: "Vacantes activas",
    value: 8,
    delta: "+2 esta semana",
  },
  {
    icon: Users,
    burbuja: "bg-aqua-300/15 text-aqua-300",
    label: "Candidatos en pipeline",
    value: 142,
    delta: "+34 hoy",
  },
  {
    icon: Zap,
    burbuja: "bg-ink-500/25 text-ink-200",
    label: "Runs de agentes (24h)",
    value: 327,
    delta: "98% éxito",
  },
  {
    icon: Activity,
    burbuja: "bg-success-500/15 text-success-500",
    label: "Costo IA hoy (USD)",
    value: "$1.42",
    delta: "12% del cap",
  },
];

// Cada etapa con su tono de la marca: del interés (aqua) a la decisión (flame).
const PIPELINE = [
  { stage: "Aplicados", count: 84, color: "bg-aqua-300/15 text-aqua-300", barra: "bg-aqua-300" },
  { stage: "Evaluados", count: 41, color: "bg-ink-400/25 text-ink-200", barra: "bg-ink-400" },
  {
    stage: "Shortlist",
    count: 12,
    color: "bg-success-500/15 text-success-500",
    barra: "bg-success-500",
  },
  { stage: "Entrevista", count: 3, color: "bg-flame-400/15 text-flame-400", barra: "bg-flame-400" },
  { stage: "Oferta", count: 2, color: "bg-flame-500/20 text-flame-500", barra: "bg-flame-500" },
];
const MAX = Math.max(...PIPELINE.map((s) => s.count));

export function App() {
  return (
    <div className="min-h-screen bg-[radial-gradient(900px_420px_at_100%_-10%,rgb(62_236_235/0.08),transparent_60%),radial-gradient(700px_380px_at_-10%_110%,rgb(254_120_2/0.07),transparent_60%)]">
      {/* Barra superior */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="container mx-auto flex h-[68px] items-center justify-between px-4 md:px-6">
          <Wordmark brand="vortex" size="sm" tone="dark" withMark />
          <div className="flex items-center gap-3">
            <Badge variant="ai">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-aqua-300" />
              Live
            </Badge>
            <Button size="sm" variant="ghost" className="gap-2.5">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-ink-600 font-mono text-[11px] font-semibold text-white">
                IR
              </span>
              Ilyra · Vector HR
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-10 md:px-6">
        {/* Encabezado */}
        <div className="mb-10 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="eyebrow">Cockpit HRBP</p>
            <h1 className="mt-3 text-3xl font-extrabold tracking-[-0.03em] md:text-[2.6rem]">
              Hola, Ilyra <span aria-hidden="true">👋</span>
            </h1>
            <p className="mt-2 text-muted-foreground">
              Esto es lo que tus agentes hicieron mientras dormías.
            </p>
          </div>
          <Button>+ Nueva vacante</Button>
        </div>

        {/* Indicadores */}
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {KPIS.map((kpi) => (
            <Card key={kpi.label}>
              <CardHeader className="pb-3">
                <span
                  className={`mb-1 grid h-10 w-10 place-items-center rounded-xl ${kpi.burbuja}`}
                >
                  <kpi.icon className="h-5 w-5" />
                </span>
                <CardDescription className="text-[13px] font-semibold">{kpi.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="font-display text-[2.1rem] font-extrabold leading-none tracking-[-0.03em] tabular-nums">
                  {kpi.value}
                </p>
                <p className="mt-2 text-[13px] text-muted-foreground">{kpi.delta}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Pipeline (placeholder) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Pipeline · Senior Software Engineer</CardTitle>
            <CardDescription>Mock — el cycle 1 conecta esto a hr-engine</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {PIPELINE.map((stage) => (
                <div
                  key={stage.stage}
                  data-etapa={stage.stage}
                  className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-border"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                      {stage.stage}
                    </p>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-bold tabular-nums ${stage.color}`}
                    >
                      {stage.count}
                    </span>
                  </div>
                  <div
                    className="mb-3 h-1.5 overflow-hidden rounded-full bg-white/10"
                    aria-hidden="true"
                  >
                    <div
                      className={`h-full rounded-full ${stage.barra}`}
                      style={{ width: `${(stage.count / MAX) * 100}%` }}
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="h-12 rounded-xl bg-muted shimmer-cyan" />
                    <div className="h-12 rounded-xl bg-muted shimmer-cyan" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
