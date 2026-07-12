"use client";

import { tokens, statusColor, SensorStatus, fontSora } from "./tokens";

type MotionState = "upright" | "moving" | "fall";

interface MotionStatusCardProps {
  state?: MotionState;
  lastUpdated?: string;
}

const stateConfig: Record<MotionState, { label: string; status: SensorStatus }> = {
  upright: { label: "Upright", status: "normal" },
  moving: { label: "Moving", status: "warning" },
  fall: { label: "Fall detected", status: "danger" },
};

// Matches Figma: Group 24, 256x112, bg #1C1F24, radius 10
export default function MotionStatusCard({
  state = "upright",
  lastUpdated = "now",
}: MotionStatusCardProps) {
  const { label, status } = stateConfig[state];
  const isCritical = state === "fall";

  return (
    <div
      className="rounded-[10px] px-5 py-[14px] w-full h-full flex flex-col transition-all duration-200 ease-out motion-card"
      style={{
        backgroundColor: tokens.bgSurface,
        border: `1px solid ${isCritical ? tokens.red : tokens.border}`,
        minHeight: 112,
        animation: isCritical ? "motion-pulse 1s ease-in-out infinite" : undefined,
      }}
    >
      <style>{`
        .motion-card:hover {
          border-color: ${isCritical ? tokens.red : tokens.navy} !important;
          box-shadow: 0 0 16px rgba(124, 147, 216, 0.06);
        }
      `}</style>
      {/* Heading: icon + title + subtitle */}
      <div className="flex items-start gap-[7px]">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="shrink-0 mt-0.5">
          <path d="M13 2L3 14h5l-2 8 10-12h-5l2-8z" stroke={tokens.textPrimary} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <div className="flex flex-col gap-[7px]">
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 15, lineHeight: "19px", color: tokens.textPrimary }}>
            Motion status
          </p>
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 10, lineHeight: "13px", color: tokens.textTertiary }}>
            Last updated {lastUpdated}
          </p>
        </div>
      </div>

      {/* Status indicator pushed to bottom */}
      <div className="flex-1" />
      <div className="flex items-center gap-1">
        <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ backgroundColor: statusColor(status) }} />
        <span style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 10, lineHeight: "13px", color: tokens.textPrimary }}>
          {label}
        </span>
      </div>

      <style>{`
        @keyframes motion-pulse {
          0%, 100% { border-color: ${tokens.red}; }
          50% { border-color: ${tokens.borderLight}; }
        }
      `}</style>
    </div>
  );
}
