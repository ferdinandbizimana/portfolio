"use client";

export default function PublicError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center">
      <h1 className="mb-2 text-2xl font-semibold">This page is temporarily unavailable</h1>
      <p className="mb-6 text-muted">Please try again in a moment.</p>
      <button type="button" className="btn-primary" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
