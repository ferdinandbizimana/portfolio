import type { Metadata } from "next";

import { Markdown } from "@/components/markdown";
import { PageShell } from "@/components/portfolio/page-shell";
import { durationText, formatPeriod, monthOf, yearsOfExperience } from "@/lib/portfolio";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "Experience" };

export default async function ExperiencePage() {
  const { experience } = await fetchPortfolio();
  const today = monthOf(new Date());
  const years = yearsOfExperience(experience, today);

  return (
    <PageShell
      eyebrow="Career"
      title="Experience"
      intro={years > 0 ? `${years}+ years of supply chain work, most recent first.` : undefined}
      width="max-w-4xl"
    >
      {experience.length === 0 ? (
        <p className="text-muted">More to come soon.</p>
      ) : (
        <ol className="relative flex flex-col gap-8 border-l-2 border-line pl-8">
          {experience.map((entry) => (
            <li key={entry.id} className="relative">
              <span
                aria-hidden
                className={`absolute top-6 -left-[41px] h-4 w-4 rounded-full border-4 border-surface ${
                  entry.end_month ? "bg-line" : "bg-accent"
                }`}
              />
              <div className="tile">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h2 className="text-lg font-semibold">{entry.role}</h2>
                  <p className="text-sm text-muted">
                    {formatPeriod(entry.start_month, entry.end_month)} ·{" "}
                    {durationText(entry.start_month, entry.end_month, today)}
                  </p>
                </div>
                <p className="mb-3 font-medium text-accent">
                  {entry.organisation}
                  {entry.location && (
                    <span className="font-normal text-muted"> · {entry.location}</span>
                  )}
                </p>
                {entry.description_md && <Markdown>{entry.description_md}</Markdown>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </PageShell>
  );
}
