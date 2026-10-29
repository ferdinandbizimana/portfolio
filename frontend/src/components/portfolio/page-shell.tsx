import type { ReactNode } from "react";

/** The page frame of every public page except the home page (which runs edge to edge). */
export function PageShell({
  eyebrow,
  title,
  intro,
  children,
  width = "max-w-6xl",
}: {
  eyebrow?: string;
  title?: string;
  intro?: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  return (
    <div className={`mx-auto w-full ${width} px-4 py-10 sm:py-14`}>
      {title && (
        <div className="mb-10 max-w-3xl">
          {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
          {intro && <div className="lead mt-3">{intro}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
