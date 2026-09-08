import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@vortex/ui";
import { Briefcase, Clock, MapPin } from "lucide-react";
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
    <main className="container mx-auto px-4 py-16">
      <header className="mb-12">
        <h1 className="mb-2 text-4xl font-black tracking-tighter md:text-5xl">Vacantes abiertas</h1>
        <p className="text-muted-foreground">
          Buscamos rebeldes que quieran liberar talento, no domesticarlo.
        </p>
      </header>

      <div className="grid gap-4">
        {VACANTES_MOCK.map((v) => (
          <Link key={v.slug} href={`/vacantes/${v.slug}`} className="block">
            <Card className="transition-shadow hover:shadow-lg">
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-xl">{v.title}</CardTitle>
                    <CardDescription className="mt-2 flex flex-wrap gap-3 text-xs">
                      <span className="flex items-center gap-1">
                        <Briefcase className="h-3 w-3" /> {v.seniority}
                      </span>
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3 w-3" /> {v.location}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" /> {v.modality}
                      </span>
                    </CardDescription>
                  </div>
                  <Badge variant="ai">Open</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{v.summary}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </main>
  );
}
