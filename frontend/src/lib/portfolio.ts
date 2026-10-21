export interface FileRef {
  id: number;
  filename: string;
  content_type: string;
  url: string;
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
