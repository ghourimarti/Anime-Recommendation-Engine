import { ImageResponse } from "next/og";

// Dynamic Open Graph image (link previews on Slack/X/Discord/etc.). Auto-detected
// by the App Router — no metadata wiring needed. Uses only the flexbox subset of
// CSS that Satori (next/og's renderer) supports; system fonts to avoid bundling.

export const alt = "ANIMA — grounded anime recommendations";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          // Satori needs backgroundColor + backgroundImage split — it rejects the
          // CSS `background` shorthand when a gradient and a solid are combined.
          backgroundColor: "#0B0B0F",
          backgroundImage:
            "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(232,179,57,0.12), rgba(11,11,15,1) 60%)",
          color: "#F4F4F5",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
          {/* The amber diamond mark. */}
          <svg width="56" height="56" viewBox="0 0 32 32">
            <path d="M16 6l10 10-10 10L6 16z" fill="#E8B339" />
          </svg>
          <span style={{ fontSize: 64, fontWeight: 700, letterSpacing: "0.05em" }}>ANIMA</span>
        </div>
        <span style={{ marginTop: 28, fontSize: 40, color: "#F4F4F5", maxWidth: 900 }}>
          Find your next anime.
        </span>
        <span style={{ marginTop: 12, fontSize: 28, color: "#A1A1AA", maxWidth: 900 }}>
          Tell us the mood — get three grounded picks, with the reasoning.
        </span>
      </div>
    ),
    { ...size },
  );
}
