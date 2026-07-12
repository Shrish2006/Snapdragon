"use client";

import { tokens, statusColor, SensorStatus, fontSora } from "./tokens";

interface StatusPillProps {
  label: string;
  value: string;
  status: SensorStatus;
}

function StatusPill({ label, value, status }: StatusPillProps) {
  return (
    <div
      className="flex-1 rounded-xl px-4 py-3 transition-all duration-200 ease-out status-pill"
      style={{ backgroundColor: tokens.bgSurface, border: `1px solid ${tokens.border}` }}
    >
      <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 12, color: tokens.textSecondary }}>{label}</p>
      <div className="flex items-center gap-1.5 mt-1.5">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor(status) }} />
        <span style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 13, color: tokens.textPrimary }}>{value}</span>
      </div>
    </div>
  );
}

// Matches Figma: Frame 20, gap 14px, height ~71px
export default function StatusStrip() {
  return (
    <>
      <style>{`
        .status-pill:hover {
          border-color: ${tokens.borderLight} !important;
          background-color: ${tokens.bgElevated} !important;
        }
      `}</style>
      <div className="flex gap-[14px] w-full">
        <StatusPill label="Helmet (FSR)" value="Worn" status="normal" />
        <StatusPill label="Sound" value="80 db" status="warning" />
        <StatusPill label="Air quality" value="Toxic" status="danger" />
      </div>
    </>
  );
}
