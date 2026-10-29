import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Markdown } from "@/components/markdown";
import { fetchProject } from "@/lib/public-api";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const project = await fetchProject((await params).slug);
  if (!project) return { title: "Not found" };
  return {
    title: project.title,
    description: project.summary || undefined,
    openGraph: project.cover ? { images: [project.cover.url] } : undefined,
  };
}

export default async function ProjectPage({ params }: Props) {
  const project = await fetchProject((await params).slug);
  if (!project) notFound();

  return (
    <article>
      <header className="bg-hero text-on-hero">
        <div className="mx-auto max-w-4xl px-4 py-12 sm:py-16">
          <Link href="/projects" className="text-sm text-white/80 no-underline hover:text-white">
            ← All case studies
          </Link>
          <p className="eyebrow mt-6 mb-2 !text-gold">Case study</p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{project.title}</h1>
          {project.summary && <p className="mt-4 text-lg text-white/85">{project.summary}</p>}
          {project.tags.length > 0 && (
            <ul className="mt-6 flex flex-wrap gap-1.5" aria-label="Tags">
              {project.tags.map((tag) => (
                <li key={tag} className="rounded-full border border-white/30 px-2.5 py-0.5 text-xs">
                  {tag}
                </li>
              ))}
            </ul>
          )}
        </div>
      </header>
      <div className="mx-auto max-w-3xl px-4 py-12">
        {project.cover && (
          <Image
            src={project.cover.url}
            alt=""
            width={960}
            height={540}
            unoptimized
            priority
            className="mb-10 w-full rounded-xl object-cover"
          />
        )}
        <div className="prose-content text-[17px]">
          <Markdown>{project.body_md}</Markdown>
        </div>
        <div className="tile mt-14 flex flex-wrap items-center justify-between gap-4">
          <p className="font-medium">Want results like these in your supply chain?</p>
          <Link href="/contact" className="btn-primary no-underline">
            Contact me
          </Link>
        </div>
      </div>
    </article>
  );
}
