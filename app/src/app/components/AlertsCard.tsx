"use client";

import { tokens, statusColor, SensorStatus, fontSora, fontMono } from "./tokens";

export interface AlertItem {
  id: string;
  label: string;
  status: SensorStatus;
  timestamp: string;
}

interface AlertsCardProps {
  alerts?: AlertItem[];
  lastUpdated?: string;
}

// Matches EnvironmentCard's shell exactly: rounded-[10px], bg #1C1F24,
// border, hover glow — the alerts feed is a new card, not a new visual
// pattern.
export default function AlertsCard({ alerts = [], lastUpdated = "—" }: AlertsCardProps) {
  return (
    <div
      className="rounded-[10px] p-5 w-full h-full flex flex-col transition-all duration-200 ease-out alerts-card"
      style={{ backgroundColor: tokens.bgSurface, border: `1px solid ${tokens.border}`, minHeight: 180 }}
    >
      <style>{`
        .alerts-card:hover {
          border-color: ${tokens.navy} !important;
          box-shadow: 0 0 20px rgba(124, 147, 216, 0.06);
        }
      `}</style>
      {/* Header: icon + title + subtitle, matches EnvironmentCard/TemperatureCard/MotionStatusCard */}
      <div className="flex items-start gap-[7px]">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke={tokens.textPrimary}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0 mt-0.5"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        <div className="flex flex-col gap-[7px]">
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 15, lineHeight: "19px", color: tokens.textPrimary }}>
            Alerts
          </p>
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 10, lineHeight: "13px", color: tokens.textTertiary }}>
            Last updated {lastUpdated}
          </p>
        </div>
      </div>

      <div className="flex-1 mt-3 flex flex-col gap-[6px] overflow-y-auto">
        {alerts.length === 0 ? (
          <p
            className="mt-1"
            style={{ fontFamily: fontSora, fontWeight: 500, fontSize: 11, color: tokens.textTertiary }}
          >
            No alerts yet
          </p>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center justify-between gap-2 rounded-md px-2.5 py-[7px]"
              style={{ backgroundColor: tokens.bgElevated }}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ backgroundColor: statusColor(alert.status) }} />
                <span
                  className="truncate"
                  style={{ fontFamily: fontSora, fontWeight: 500, fontSize: 11, color: tokens.textPrimary }}
                >
                  {alert.label}
                </span>
              </div>
              <span
                className="shrink-0"
                style={{ fontFamily: fontMono, fontWeight: 500, fontSize: 9, color: tokens.textTertiary }}
              >
                {alert.timestamp}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
