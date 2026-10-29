import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { Markdown } from "@/components/markdown";
import { CredentialList } from "@/components/portfolio/credentials";
import { PageShell } from "@/components/portfolio/page-shell";
import { monthOf, yearsOfExperience } from "@/lib/portfolio";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "About" };

export default async function AboutPage() {
  const { profile, experience } = await fetchPortfolio();
  const text = profile.about_md || profile.summary_md;
  const years = yearsOfExperience(experience, monthOf(new Date()));
  const credentials = [...profile.certifications, ...profile.education];
  const facts: [string, string][] = [
    ["Based in", profile.location],
    ["Experience", years > 0 ? `${years}+ years` : ""],
    ["Languages", profile.languages.join(", ")],
    ["Availability", profile.availability],
  ].filter((fact): fact is [string, string] => Boolean(fact[1]));

  return (
    <PageShell
      eyebrow="About"
      title={`About ${profile.full_name.split(" ")[0] ?? profile.full_name}`}
    >
      <div className="grid gap-10 lg:grid-cols-[1fr_320px]">
        <article className="max-w-3xl">
          {text ? <Markdown>{text}</Markdown> : <p className="text-muted">More to come soon.</p>}
          {credentials.length > 0 && (
            <section aria-labelledby="credentials-heading" className="mt-12">
              <h2 id="credentials-heading" className="mb-5 text-xl font-semibold">
                Certifications and education
              </h2>
              <CredentialList items={credentials} />
            </section>
          )}
        </article>
        <aside className="tile flex h-fit flex-col gap-5 lg:sticky lg:top-24">
          {profile.photo && (
            <Image
              src={profile.photo.url}
              alt={`Photo of ${profile.full_name}`}
              width={320}
              height={320}
              unoptimized
              className="aspect-square w-full rounded-lg object-cover"
            />
          )}
          {facts.length > 0 && (
            <dl className="grid gap-3 text-sm">
              {facts.map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-semibold tracking-wide text-muted uppercase">
                    {label}
                  </dt>
                  <dd className="mt-0.5">{value}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="flex flex-wrap gap-2">
            {profile.cv && (
              <a href={profile.cv.url} className="btn-primary no-underline">
                Download CV (PDF)
              </a>
            )}
            <Link href="/contact" className="btn-secondary no-underline">
              Contact me
            </Link>
          </div>
        </aside>
      </div>
    </PageShell>
  );
}
