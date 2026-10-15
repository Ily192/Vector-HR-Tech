import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@vortex/ui";
import { ArrowRight, Briefcase, Clock, MapPin } from "lucide-react";
import Link from "next/link";

// Placeholder — sustituir por fetch a Supabase en cycle 1
const VACANTES_MOCK = [
  {
    slug: "senior-software-engineer",
    title: "Senior Software Engineer",
    location: "Remote · LATAM",
    seniority: "senior",
    modality: "remote",
    summary: "Liderar arquitectura de servicios Python/FastAPI en multi-tenant SaaS.",
  },
  {
    slug: "hr-business-partner",
    title: "HR Business Partner",
    location: "CDMX · Híbrido",
    seniority: "semi-senior",
    modality: "hybrid",
    summary: "Acompañar líderes de tecnología en ciclos de talento end-to-end.",
  },
];

export const metadata = { title: "Vacantes abiertas" };

export default function VacantesPage() {
  return (
    <main className="container mx-auto max-w-4xl px-4 py-14 md:px-6 md:py-20">
      <header className="mb-10">
        <span className="eyebrow">{VACANTES_MOCK.length} vacantes abiertas</span>
        <h1 className="mt-3 text-4xl font-extrabold tracking-[-0.035em] md:text-5xl">
          Vacantes abiertas
        </h1>
        <p className="mt-3 max-w-xl text-lg text-muted-foreground">
          Buscamos rebeldes que quieran liberar talento, no domesticarlo.
        </p>
      </header>

      <div className="grid gap-4">
        {VACANTES_MOCK.map((v) => (
          <Link
            key={v.slug}
            href={`/vacantes/${v.slug}`}
            className="group block rounded-[20px] focus-visible:outline-none"
          >
            <Card className="transition-[box-shadow,border-color,transform] duration-normal group-hover:-translate-y-0.5 group-hover:border-ink-200 group-hover:shadow-lift">
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-xl">{v.title}</CardTitle>
                    <CardDescription className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[13px] font-semibold">
                      <span className="flex items-center gap-1.5">
                        <Briefcase className="h-3.5 w-3.5" /> {v.seniority}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <MapPin className="h-3.5 w-3.5" /> {v.location}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" /> {v.modality}
                      </span>
                    </CardDescription>
                  </div>
                  <Badge variant="ai">Open</Badge>
                </div>
              </CardHeader>
              <CardContent className="flex items-end justify-between gap-4">
                <p className="text-[15px] text-muted-foreground">{v.summary}</p>
                <ArrowRight className="h-5 w-5 shrink-0 text-mist-500 transition-transform group-hover:translate-x-1 group-hover:text-ink-900" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </main>
  );
}
