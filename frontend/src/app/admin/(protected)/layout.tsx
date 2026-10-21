import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { getCurrentUser } from "@/lib/server-api";

import { AdminNav, type NavItem } from "./admin-nav";
import { LogoutButton } from "./logout-button";

export const metadata: Metadata = {
  title: { template: "%s · Admin", default: "Admin" },
  robots: { index: false },
};
export const dynamic = "force-dynamic";

const NAV: NavItem[] = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/activity", label: "Activity log" },
  { href: "/admin/settings", label: "Settings" },
];

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/admin/login");

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-line bg-surface p-4 md:min-h-screen md:w-56 md:border-r md:border-b-0">
        <div className="mb-3 flex items-center justify-between gap-2 md:mb-6 md:block">
          <Link href="/admin" className="font-semibold">
            Admin
          </Link>
          <p className="truncate text-xs text-muted md:mt-1" title={user.email}>
            {user.email}
          </p>
        </div>
        <AdminNav items={NAV} />
        <div className="mt-3 md:mt-6">
          <LogoutButton />
        </div>
      </aside>
      <main className="flex-1 px-4 py-6 md:px-8">{children}</main>
    </div>
  );
}
