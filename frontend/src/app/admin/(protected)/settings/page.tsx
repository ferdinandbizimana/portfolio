import { apiGet } from "@/lib/server-api";

import { MailTest } from "./mail-test";
import { PasswordForm } from "./password-form";

export const metadata = { title: "Settings" };

interface MailStatus {
  configured: boolean;
  recipient: string;
  smtp_host: string;
}

export default async function SettingsPage() {
  const response = await apiGet("/api/admin/mail");
  const mail = response.ok ? ((await response.json()) as MailStatus) : null;

  return (
    <div className="flex max-w-3xl flex-col gap-10">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <section aria-labelledby="password-heading">
        <h2 id="password-heading" className="mb-1 text-lg font-semibold">
          Password
        </h2>
        <p className="mb-4 text-sm text-muted">
          Your password is the only key to this area. Use a long one that you do not use anywhere
          else.
        </p>
        <PasswordForm />
      </section>
      <section aria-labelledby="mail-heading">
        <h2 id="mail-heading" className="mb-1 text-lg font-semibold">
          Contact form e-mail
        </h2>
        {mail?.configured ? (
          <p className="mb-4 text-sm text-muted">
            Messages from the contact form are sent to <strong>{mail.recipient}</strong> through{" "}
            {mail.smtp_host}.
          </p>
        ) : (
          <p className="mb-4 text-sm text-muted">
            E-mail is not set up yet. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, MAIL_FROM and
            CONTACT_TO_EMAIL in the server&apos;s .env file (see docs/operations.md), then restart.
          </p>
        )}
        <MailTest />
      </section>
    </div>
  );
}
