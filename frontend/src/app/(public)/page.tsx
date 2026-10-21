import { fetchHealth } from "@/lib/health";

// Placeholder home page for Phase 1. The portfolio is built in Phase 3.
export const dynamic = "force-dynamic";

const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export default async function HomePage() {
  const health = await fetchHealth(API_URL);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold">Ferdinand Bizimana</h1>
      <p className="text-muted">
        Supply chain professional working with SAP S/4HANA (MM, EWM, SD, FI). The portfolio and
        dashboards will appear here.
      </p>
      <section aria-labelledby="status" className="rounded-lg bg-panel p-4">
        <h2 id="status" className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
          System status
        </h2>
        <p data-testid="api-status">
          API: <strong>{health.status}</strong>
        </p>
        <ul className="mt-1 text-sm text-muted">
          {Object.entries(health.checks).map(([name, state]) => (
            <li key={name}>
              {name}: {state}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
