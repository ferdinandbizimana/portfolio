import Link from "next/link";

import { formatDateTime } from "@/lib/audit";
import { fetchHealth } from "@/lib/health";
import { API_URL, apiGet, getCurrentUser } from "@/lib/server-api";
import { STATE_CLASS, STATE_LABEL, type SystemStatus } from "@/lib/system";

export const metadata = { title: "Overview" };

const SECTIONS = [
  { href: "/admin/content/profile", title: "Profile", text: "Name, introduction, photo and CV." },
  { href: "/admin/content/experience", title: "Experience", text: "Your roles, in order." },
  { href: "/admin/content/skills", title: "Skills", text: "Groups of skills." },
  {
    href: "/admin/content/projects",
    title: "Projects",
    text: "Case studies; publish when ready.",
  },
  { href: "/admin/data", title: "Data files", text: "Upload SAP exports (Excel or CSV)." },
  { href: "/admin/analyses", title: "Analyses", text: "Run an analysis on uploaded files." },
  { href: "/admin/runs", title: "Runs", text: "Results, checks, reports; compare periods." },
  {
    href: "/admin/schedules",
    title: "Schedules",
    text: "Automatic runs on files from the shared folder.",
  },
  { href: "/admin/templates", title: "Templates", text: "Word and PowerPoint templates." },
  {
    href: "/admin/publications",
    title: "Published",
    text: "Dashboards shared by link or on the public site.",
  },
  {
    href: "/admin/activity",
    title: "Activity log",
    text: "Sign-ins, failed attempts and changes.",
  },
  { href: "/admin/settings", title: "Settings", text: "Password and e-mail." },
];

export default async function AdminHome() {
  const [user, health, systemResponse] = await Promise.all([
    getCurrentUser(),
    fetchHealth(API_URL),
    apiGet("/api/admin/system").catch(() => null),
  ]);
  const system = systemResponse?.ok ? ((await systemResponse.json()) as SystemStatus) : null;

  return (
    <div className="max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold">Overview</h1>
      <p className="mb-6 text-muted">
        {user?.last_login_at
          ? `Previous sign-in: ${formatDateTime(user.last_login_at)} (Kigali time).`
          : "Welcome. This is your first sign-in."}
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {SECTIONS.map((section) => (
          <Link key={section.href} href={section.href} className="card">
            <h2 className="font-semibold">{section.title}</h2>
            <p className="text-sm text-muted">{section.text}</p>
          </Link>
        ))}
      </div>
      <section aria-labelledby="status-heading" className="mt-8 rounded-lg bg-panel p-4 text-sm">
        <h2 id="status-heading" className="mb-2 font-semibold">
          System status: {health.status === "ok" ? "database and job queue running" : health.status}
        </h2>
        <ul className="flex flex-col gap-1">
          {Object.entries(health.checks).map(([name, state]) => (
            <li key={name} className="text-muted">
              {name}: {state}
            </li>
          ))}
          {system?.items.map((item) => (
            <li key={item.name}>
              <span className={`mr-2 rounded-full px-2 py-0.5 text-xs ${STATE_CLASS[item.state]}`}>
                {STATE_LABEL[item.state]}
              </span>
              <span className="font-medium">{item.name}</span>: {item.detail}
            </li>
          ))}
        </ul>
        {system && <p className="mt-2 text-xs text-muted">Version {system.version}</p>}
      </section>
    </div>
  );
}
