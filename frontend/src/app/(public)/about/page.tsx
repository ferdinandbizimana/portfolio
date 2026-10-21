import type { Metadata } from "next";
import Image from "next/image";

import { Markdown } from "@/components/markdown";
import { fetchPortfolio } from "@/lib/public-api";

export const metadata: Metadata = { title: "About" };

export default async function AboutPage() {
  const { profile } = await fetchPortfolio();
  const text = profile.about_md || profile.summary_md;

  return (
    <article className="flex flex-col gap-8 sm:flex-row-reverse sm:items-start">
      {profile.photo && (
        <Image
          src={profile.photo.url}
          alt={`Photo of ${profile.full_name}`}
          width={240}
          height={240}
          unoptimized
          className="h-48 w-48 rounded-lg object-cover"
        />
      )}
      <div className="flex-1">
        <h1 className="mb-6 text-3xl font-semibold">About</h1>
        {text ? <Markdown>{text}</Markdown> : <p className="text-muted">More to come soon.</p>}
        {profile.cv && (
          <p className="mt-8">
            <a href={profile.cv.url} className="btn-secondary">
              Download CV (PDF)
            </a>
          </p>
        )}
      </div>
    </article>
  );
}
