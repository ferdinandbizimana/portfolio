import { PasswordForm } from "./password-form";

export const metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="mb-6 text-2xl font-semibold">Settings</h1>
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
    </div>
  );
}
