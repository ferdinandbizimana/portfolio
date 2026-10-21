import type { Metadata } from "next";

import { Markdown } from "@/components/markdown";
import { formatPeriod } from "@/lib/portfolio";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "Experience" };

export default async function ExperiencePage() {
  const { experience } = await fetchPortfolio();

  return (
    <div>
      <h1 className="mb-8 text-3xl font-semibold">Experience</h1>
      {experience.length === 0 ? (
        <p className="text-muted">More to come soon.</p>
      ) : (
        <ol className="flex flex-col gap-10 border-l-2 border-line pl-6">
          {experience.map((entry) => (
            <li key={entry.id} className="relative">
              <span
                aria-hidden
                className="absolute -left-[31px] top-1.5 h-3 w-3 rounded-full border-2 border-accent bg-surface"
              />
              <h2 className="text-lg font-semibold">{entry.role}</h2>
              <p className="text-muted">
                {entry.organisation}
                {entry.location && ` · ${entry.location}`}
              </p>
              <p className="mb-3 text-sm text-muted">
                {formatPeriod(entry.start_month, entry.end_month)}
              </p>
              {entry.description_md && <Markdown>{entry.description_md}</Markdown>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
