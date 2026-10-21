import Link from "next/link";

import { formatDateTime } from "@/lib/audit";
import { getCurrentUser } from "@/lib/server-api";

export const metadata = { title: "Overview" };

export default async function AdminHome() {
  const user = await getCurrentUser();

  return (
    <div className="max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold">Overview</h1>
      <p className="mb-6 text-muted">
        {user?.last_login_at
          ? `Previous sign-in: ${formatDateTime(user.last_login_at)} (Kigali time).`
          : "Welcome. This is your first sign-in."}
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/admin/activity" className="card">
          <h2 className="font-semibold">Activity log</h2>
          <p className="text-sm text-muted">
            Sign-ins, failed attempts and other important actions.
          </p>
        </Link>
        <Link href="/admin/settings" className="card">
          <h2 className="font-semibold">Settings</h2>
          <p className="text-sm text-muted">Change your password.</p>
        </Link>
      </div>
    </div>
  );
}
