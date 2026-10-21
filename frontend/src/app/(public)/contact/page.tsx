import type { Metadata } from "next";

import { ContactForm } from "./contact-form";

export const metadata: Metadata = { title: "Contact" };

export default function ContactPage() {
  return (
    <div className="mx-auto max-w-xl">
      <h1 className="mb-2 text-3xl font-semibold">Contact</h1>
      <p className="mb-8 text-muted">
        Send me a message and I will reply by e-mail as soon as I can.
      </p>
      <ContactForm />
    </div>
  );
}
