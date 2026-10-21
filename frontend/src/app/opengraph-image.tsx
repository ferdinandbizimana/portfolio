import { ImageResponse } from "next/og";

import { fetchPortfolio } from "@/lib/public-api";

export const dynamic = "force-dynamic";
export const alt = "Ferdinand Bizimana, supply chain and SAP S/4HANA";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** The preview image shown when a link to the site is shared. */
export default async function OpenGraphImage() {
  let name = "Ferdinand Bizimana";
  let headline = "Supply chain professional · SAP S/4HANA";
  try {
    const { profile } = await fetchPortfolio();
    name = profile.full_name;
    headline = profile.headline || headline;
  } catch {
    // Use the defaults when the API is not reachable.
  }
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: 80,
        background: "#0b3a41",
        color: "#ffffff",
      }}
    >
      <div style={{ fontSize: 72, fontWeight: 700 }}>{name}</div>
      <div style={{ fontSize: 36, marginTop: 24, color: "#cfe3e6" }}>{headline}</div>
    </div>,
    size,
  );
}
