import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Markdown } from "@/components/markdown";
import { Tags } from "@/components/project-card";
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
    <article className="mx-auto max-w-3xl">
      <Link href="/projects" className="text-sm">
        ← All projects
      </Link>
      <h1 className="mb-3 mt-4 text-3xl font-semibold">{project.title}</h1>
      {project.summary && <p className="mb-4 text-lg text-muted">{project.summary}</p>}
      {project.tags.length > 0 && <Tags tags={project.tags} />}
      {project.cover && (
        <Image
          src={project.cover.url}
          alt=""
          width={960}
          height={540}
          unoptimized
          priority
          className="my-8 w-full rounded-lg object-cover"
        />
      )}
      <div className="mt-8">
        <Markdown>{project.body_md}</Markdown>
      </div>
    </article>
  );
}
