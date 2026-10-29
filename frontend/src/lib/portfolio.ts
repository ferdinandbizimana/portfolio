export interface FileRef {
  id: number;
  filename: string;
  content_type: string;
  url: string;
}

/** A key result shown large on the home page, e.g. "99%" / "inventory accuracy". */
export interface Highlight {
  value: string;
  label: string;
}

/** A certification or a degree. */
export interface Credential {
  title: string;
  issuer: string;
  year: string;
}

export interface Profile {
  full_name: string;
  headline: string;
  location: string;
  summary_md: string;
  about_md: string;
  linkedin_url: string;
  github_url: string;
  photo: FileRef | null;
  cv: FileRef | null;
  availability: string;
  highlights: Highlight[];
  certifications: Credential[];
  education: Credential[];
  languages: string[];
}

export interface Experience {
  id: number;
  role: string;
  organisation: string;
  location: string;
  start_month: string;
  end_month: string | null;
  description_md: string;
}

export interface SkillGroup {
  id: number;
  name: string;
  items: string[];
}

export interface ProjectSummary {
  id: number;
  slug: string;
  title: string;
  summary: string;
  tags: string[];
  cover: FileRef | null;
  published: boolean;
  featured: boolean;
}

export interface Project extends ProjectSummary {
  body_md: string;
  cover_file_id: number | null;
}

export interface Portfolio {
  profile: Profile;
  experience: Experience[];
  skills: SkillGroup[];
  projects: ProjectSummary[];
}

/** Cache tag of every public portfolio fetch; refreshed after each admin edit. */
export const PORTFOLIO_TAG = "portfolio";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2023-07" → "Jul 2023". */
export function formatMonth(month: string): string {
  const [year, monthNumber] = month.split("-");
  const name = MONTHS[Number(monthNumber) - 1];
  return name && year ? `${name} ${year}` : month;
}

/** "Jul 2023 – Present" or "Mar 2021 – Jun 2023". */
export function formatPeriod(start: string, end: string | null): string {
  return `${formatMonth(start)} – ${end ? formatMonth(end) : "Present"}`;
}

/** Turn a title into a URL slug: "Stock Count 2026!" → "stock-count-2026". */
export function slugify(title: string): string {
  return title
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
}

/** Skills typed one per line (commas also work), without blanks or duplicates. */
export function parseItems(text: string): string[] {
  const items = text
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return [...new Set(items)];
}

function monthIndex(month: string): number {
  const [year, number] = month.split("-").map(Number);
  return (year ?? 0) * 12 + ((number ?? 1) - 1);
}

/** "2023-07" for a date (the month a role "until now" runs to). */
export function monthOf(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

/** Whole years from the first role to today (overlapping roles count once). */
export function yearsOfExperience(
  entries: Pick<Experience, "start_month" | "end_month">[],
  today: string,
): number {
  if (entries.length === 0) return 0;
  const first = Math.min(...entries.map((e) => monthIndex(e.start_month)));
  return Math.max(0, Math.floor((monthIndex(today) - first + 1) / 12));
}

/** "2 yrs 4 mos", "11 mos", "1 yr": the length of a role, both months included. */
export function durationText(start: string, end: string | null, today: string): string {
  const months = Math.max(1, monthIndex(end ?? today) - monthIndex(start) + 1);
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [
    years ? `${years} ${years === 1 ? "yr" : "yrs"}` : "",
    rest ? `${rest} ${rest === 1 ? "mo" : "mos"}` : "",
  ];
  return parts.filter(Boolean).join(" ");
}

/** "AB" from "Ada Bizimana": the monogram in the site header. */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** Fields added later default to empty, so a response cached before an update still renders. */
export function withProfileDefaults(portfolio: Portfolio): Portfolio {
  const profile = portfolio.profile;
  return {
    ...portfolio,
    profile: {
      ...profile,
      availability: profile.availability ?? "",
      highlights: profile.highlights ?? [],
      certifications: profile.certifications ?? [],
      education: profile.education ?? [],
      languages: profile.languages ?? [],
    },
  };
}
