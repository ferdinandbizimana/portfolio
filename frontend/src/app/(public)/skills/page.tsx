import type { Metadata } from "next";

import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "Skills" };

export default async function SkillsPage() {
  const { skills } = await fetchPortfolio();

  return (
    <div>
      <h1 className="mb-8 text-3xl font-semibold">Skills</h1>
      {skills.length === 0 ? (
        <p className="text-muted">More to come soon.</p>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2">
          {skills.map((group) => (
            <section key={group.id} className="rounded-lg border border-line p-4">
              <h2 className="mb-3 font-semibold">{group.name}</h2>
              <ul className="flex flex-wrap gap-2">
                {group.items.map((item) => (
                  <li key={item} className="rounded-full bg-panel px-3 py-1 text-sm">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
