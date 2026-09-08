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
import { ArrowRight, Shield, Sparkles, Zap } from "lucide-react";
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen">
      {/* Hero — modo dark con cian dark + glow */}
      <section className="relative overflow-hidden bg-vector-cian-dark-500 text-white">
        <div className="pointer-events-none absolute inset-0 opacity-30">
          <div className="absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-vector-cian-electric-500 blur-3xl" />
        </div>
        <div className="container relative mx-auto px-4 py-24 md:py-32">
          <div className="mx-auto max-w-4xl text-center">
            <div className="mb-8 flex justify-center">
              <Wordmark brand="vortex" size="lg" />
            </div>

            <Badge variant="ai" className="mb-6">
              <Sparkles className="h-3 w-3" />
              Powered by agentic AI
            </Badge>

            <h1 className="mb-6 text-4xl font-black leading-[1.05] tracking-tighter md:text-6xl">
              Hackeando la rutina,
              <br />
              <span className="bg-gradient-to-r from-vector-orange-500 to-vector-cian-electric-500 bg-clip-text text-transparent">
                liberando el talento
              </span>
            </h1>

            <p className="mx-auto mb-10 max-w-2xl text-lg text-white/80 md:text-xl">
              El Operations Engine agentic que ejecuta tus procesos de HR, Sales y operaciones
              end-to-end. Multi-canal, multi-tenant, self-hostable.
            </p>

            <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
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
        </div>
      </section>

      {/* Pillars */}
      <section className="container mx-auto px-4 py-20">
        <div className="mb-12 text-center">
          <h2 className="mb-4 text-3xl font-black tracking-tighter md:text-4xl">
            Tres pilares, una sola plataforma
          </h2>
          <p className="text-muted-foreground">
            Autoridad, rebeldía y jovialidad — sin la rigidez del HR tech tradicional.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Card>
            <CardHeader>
              <Zap className="mb-2 h-8 w-8 text-vector-orange-500" />
              <CardTitle>Velocidad</CardTitle>
              <CardDescription>
                Agentes autónomos que procesan candidatos en minutos, no semanas.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>• Sourcing 24/7</li>
                <li>• Scoring vectorial + AI</li>
                <li>• Onboarding automatizado</li>
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <Sparkles className="mb-2 h-8 w-8 text-vector-cian-electric-700 dark:text-vector-cian-electric-500" />
              <CardTitle>Inteligencia</CardTitle>
              <CardDescription>
                LLMs orquestados con governance, no prompts sueltos.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>• Skills versionadas con evals</li>
                <li>• Multi-modelo (OpenAI + Gemini + Claude)</li>
                <li>• Cost cap por tenant</li>
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <Shield className="mb-2 h-8 w-8 text-vector-cian-dark-500 dark:text-vector-cian-electric-500" />
              <CardTitle>Control</CardTitle>
              <CardDescription>
                Multi-tenant, self-hostable, audit log en cada paso.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>• RLS Postgres nativo</li>
                <li>• Run-tokens JWT 5 min</li>
                <li>• LGPD / Habeas Data ready</li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t bg-vector-cian-dark-50 dark:bg-vector-cian-dark-900">
        <div className="container mx-auto flex flex-col items-center justify-between gap-4 px-4 py-8 md:flex-row">
          <Wordmark brand="vector" size="sm" />
          <p className="text-sm text-muted-foreground">
            © {new Date().getFullYear()} Vector HR Tech · Hecho en LATAM
          </p>
        </div>
      </footer>
    </main>
  );
}
