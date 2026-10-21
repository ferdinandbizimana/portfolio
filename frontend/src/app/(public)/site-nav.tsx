"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function SiteNav({ links }: { links: { href: string; label: string }[] }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto text-sm">
      {links.map((link) => {
        const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap rounded-md px-2 py-1 ${
              active ? "bg-panel font-medium text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
