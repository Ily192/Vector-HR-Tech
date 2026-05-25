import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Wordmark } from "@vortex/ui";
import { Activity, Briefcase, Users, Zap } from "lucide-react";

const KPIS = [
  { icon: Briefcase, label: "Vacantes activas", value: 8, delta: "+2 esta semana" },
  { icon: Users, label: "Candidatos en pipeline", value: 142, delta: "+34 hoy" },
  { icon: Zap, label: "Runs de agentes (24h)", value: 327, delta: "98% éxito" },
  { icon: Activity, label: "Costo IA hoy (USD)", value: "$1.42", delta: "12% del cap" },
];

const PIPELINE = [
  { stage: "Aplicados", count: 84, color: "bg-vector-cian-electric-500/20 text-vector-cian-electric-500" },
  { stage: "Evaluados", count: 41, color: "bg-vector-orange-500/20 text-vector-orange-500" },
  { stage: "Shortlist", count: 12, color: "bg-success-500/20 text-success-500" },
  { stage: "Entrevista", count: 3, color: "bg-warning-500/20 text-warning-500" },
  { stage: "Oferta", count: 2, color: "bg-vector-cian-electric-500/20 text-vector-cian-electric-500" },
];

export function App() {
  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <header className="border-b border-border bg-card">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <Wordmark brand="vortex" size="md" />
          <div className="flex items-center gap-3">
            <Badge variant="ai">
              <Activity className="h-3 w-3" /> Live
            </Badge>
            <Button size="sm" variant="ghost">
              Ilyra · Vector HR
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        {/* Heading */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Cockpit HRBP</p>
            <h1 className="text-3xl font-black tracking-tighter md:text-4xl">
              Hola, Ilyra <span className="text-vector-orange-500">👋</span>
            </h1>
            <p className="mt-2 text-muted-foreground">
              Esto es lo que tus agentes hicieron mientras dormías.
            </p>
          </div>
          <Button>+ Nueva vacante</Button>
        </div>

        {/* KPIs */}
        <div className="mb-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {KPIS.map((kpi) => (
            <Card key={kpi.label}>
              <CardHeader className="pb-3">
                <kpi.icon className="h-5 w-5 text-vector-cian-electric-500" />
                <CardDescription className="text-xs uppercase tracking-wide">
                  {kpi.label}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="font-display text-3xl font-black">{kpi.value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{kpi.delta}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Pipeline kanban (placeholder) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Pipeline · Senior Software Engineer</CardTitle>
            <CardDescription>Mock — el cycle 1 conecta esto a hr-engine</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
              {PIPELINE.map((stage) => (
                <div key={stage.stage} className="rounded-lg border border-border bg-background p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {stage.stage}
                    </p>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${stage.color}`}>
                      {stage.count}
                    </span>
                  </div>
                  <div className="space-y-2">
                    <div className="h-12 rounded bg-muted shimmer-cyan" />
                    <div className="h-12 rounded bg-muted shimmer-cyan" />
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
