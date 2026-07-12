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

interface StatusStripProps {
  sound?: { value: string; status: SensorStatus } | null;
  airQuality?: { value: string; status: SensorStatus } | null;
  gatewayHealth?: { value: string; status: SensorStatus } | null;
}

// Matches Figma: Frame 20, gap 14px, height ~71px
export default function StatusStrip({ sound, airQuality, gatewayHealth }: StatusStripProps) {
  return (
    <>
      <style>{`
        .status-pill:hover {
          border-color: ${tokens.borderLight} !important;
          background-color: ${tokens.bgElevated} !important;
        }
      `}</style>
      <div className="flex gap-[14px] w-full">
        <StatusPill label="Helmet (FSR)" value="No sensor" status="unknown" />
        <StatusPill label="Sound" value={sound?.value ?? "—"} status={sound?.status ?? "unknown"} />
        <StatusPill label="Air quality" value={airQuality?.value ?? "—"} status={airQuality?.status ?? "unknown"} />
        <StatusPill label="Gateway" value={gatewayHealth?.value ?? "—"} status={gatewayHealth?.status ?? "unknown"} />
      </div>
    </>
  );
}
