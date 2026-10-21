import type { Profile } from "@/lib/portfolio";
import { apiGet } from "@/lib/server-api";

import { ProfileForm } from "./profile-form";

export const metadata = { title: "Profile" };

export default async function ProfileAdminPage() {
  const response = await apiGet("/api/admin/content/profile");
  if (!response.ok) return <p role="alert">The profile could not be loaded.</p>;
  const profile = (await response.json()) as Profile;

  return (
    <div>
      <h1 className="mb-2 text-2xl font-semibold">Profile</h1>
      <p className="mb-6 text-muted">Your name, introduction, photo and CV on the public site.</p>
      <ProfileForm initial={profile} />
    </div>
  );
}
