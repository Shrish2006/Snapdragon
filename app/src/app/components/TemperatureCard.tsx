"use client";

import { tokens, fontSora, fontMono } from "./tokens";

interface TemperatureCardProps {
  bodyTemp?: number | null;
  ambientTemp?: number | null;
  lastUpdated?: string;
}

// Matches Figma: Group 29, 256x136, bg #1C1F24, radius 10
export default function TemperatureCard({
  bodyTemp = null,
  ambientTemp = null,
  lastUpdated = "—",
}: TemperatureCardProps) {
  return (
    <div
      className="rounded-[10px] px-5 py-[14px] w-full h-full flex flex-col transition-all duration-200 ease-out temp-card"
      style={{ backgroundColor: tokens.bgSurface, border: `1px solid ${tokens.border}`, minHeight: 136 }}
    >
      <style>{`
        .temp-card:hover {
          border-color: ${tokens.navy} !important;
          box-shadow: 0 0 16px rgba(124, 147, 216, 0.06);
        }
      `}</style>
      {/* Heading: thermometer icon + title + subtitle */}
      <div className="flex items-start gap-[7px]">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={tokens.textPrimary} strokeWidth="1.8" strokeLinecap="round" className="shrink-0 mt-0.5">
          <path d="M14 14.76V3.5a2 2 0 0 0-4 0v11.26a4 4 0 1 0 4 0Z" />
        </svg>
        <div className="flex flex-col gap-[7px]">
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 15, lineHeight: "19px", color: tokens.textPrimary }}>
            Temperature
          </p>
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 10, lineHeight: "13px", color: tokens.textTertiary }}>
            Last updated {lastUpdated}
          </p>
        </div>
      </div>

      {/* Gap before values */}
      <div className="flex-1" />

      {/* Body / Ambient values row */}
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <span style={{ fontFamily: fontMono, fontWeight: 500, fontSize: 10, lineHeight: "13px", color: tokens.textPrimary }}>
            Body
          </span>
          <span style={{ fontFamily: fontMono, fontWeight: 500, fontSize: 7, lineHeight: "9px", color: tokens.textTertiary }}>
            {bodyTemp !== null ? `${bodyTemp}°C` : "No sensor"}
          </span>
        </div>

        <div className="w-px self-stretch" style={{ backgroundColor: tokens.border }} />

        <div className="flex flex-col">
          <span style={{ fontFamily: fontMono, fontWeight: 500, fontSize: 10, lineHeight: "13px", color: tokens.textPrimary }}>
            Ambient
          </span>
          <span style={{ fontFamily: fontMono, fontWeight: 500, fontSize: 7, lineHeight: "9px", color: tokens.textTertiary }}>
            {ambientTemp !== null ? `${ambientTemp}°C` : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
