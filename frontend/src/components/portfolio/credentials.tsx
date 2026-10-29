import type { Credential } from "@/lib/portfolio";

/** Certifications or degrees: title, then issuer and year. */
export function CredentialList({ items }: { items: Credential[] }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <li key={`${item.title}-${item.issuer}-${item.year}`} className="tile flex gap-3">
          <span
            aria-hidden
            className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-bold text-accent"
          >
            ✓
          </span>
          <span>
            <span className="block font-semibold">{item.title}</span>
            {(item.issuer || item.year) && (
              <span className="block text-sm text-muted">
                {[item.issuer, item.year].filter(Boolean).join(" · ")}
              </span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
