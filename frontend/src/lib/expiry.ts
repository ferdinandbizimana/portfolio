// Monthly expiry follow-up: shapes returned by /api/admin/expiry and /api/public/expiry.

export interface ExpiryItem {
  id: number;
  material: string;
  description: string;
  owner: string;
  plants: string;
  value: number;
  root_cause: string;
  reason: string;
  justified_by: string;
  justified_at: string | null;
}

export interface PlantOutlook {
  plant: string;
  plant_name: string;
  expired: number;
  within_3_months: number;
  three_to_6_months: number;
}

export interface ExpiryReview {
  id: number;
  run_id: number;
  closing_date: string;
  mailed_month: string;
  mailed_at: string | null;
  items: number;
  justified: number;
  expired_value: number;
  link: string;
}

export interface ExpiryRunRow {
  run_id: number;
  label: string;
  opening_date: string;
  closing_date: string;
  created_at: string;
  review: ExpiryReview | null;
}

export interface ExpiryOverview {
  runs: ExpiryRunRow[];
  mail_ready: boolean;
  root_causes: string[];
}

export interface ExpiryDetail {
  review: ExpiryReview;
  items: ExpiryItem[];
  outlook: PlantOutlook[];
  root_causes: string[];
}

/** "RWF 1,234,567" (no decimals; money is kept in full in the data). */
export function rwf(value: number): string {
  return `RWF ${Math.round(value).toLocaleString("en-US")}`;
}

/** The root cause that needs the reason written out. */
export function needsReason(rootCauses: string[], cause: string): boolean {
  return cause !== "" && cause === rootCauses[rootCauses.length - 1];
}
