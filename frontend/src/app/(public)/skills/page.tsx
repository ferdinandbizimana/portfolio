import type { Metadata } from "next";

import { CredentialList } from "@/components/portfolio/credentials";
import { PageShell } from "@/components/portfolio/page-shell";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "Skills" };

export default async function SkillsPage() {
  const { profile, skills } = await fetchPortfolio();

  return (
    <PageShell
      eyebrow="Toolkit"
      title="Skills"
      intro="The systems, methods and tools I use to keep stock accurate, available and accounted for."
    >
      {skills.length === 0 ? (
        <p className="text-muted">More to come soon.</p>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((group) => (
            <section key={group.id} className="tile">
              <h2 className="mb-4 font-semibold">{group.name}</h2>
              <ul className="flex flex-wrap gap-2">
                {group.items.map((item) => (
                  <li key={item} className="chip">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {profile.certifications.length > 0 && (
        <section aria-labelledby="certifications-heading" className="mt-14">
          <h2 id="certifications-heading" className="section-title mb-6">
            Certifications
          </h2>
          <CredentialList items={profile.certifications} />
        </section>
      )}
      {profile.education.length > 0 && (
        <section aria-labelledby="education-heading" className="mt-14">
          <h2 id="education-heading" className="section-title mb-6">
            Education
          </h2>
          <CredentialList items={profile.education} />
        </section>
      )}
      {profile.languages.length > 0 && (
        <section aria-labelledby="languages-heading" className="mt-14">
          <h2 id="languages-heading" className="section-title mb-6">
            Languages
          </h2>
          <ul className="flex flex-wrap gap-2">
            {profile.languages.map((language) => (
              <li key={language} className="chip">
                {language}
              </li>
            ))}
          </ul>
        </section>
      )}
    </PageShell>
  );
}
