"use client";

import { tokens, fontSora } from "./tokens";

interface Metric {
  label: string;
  color: string;
  points: string; // SVG polyline points, placeholder data
}

const metrics: Metric[] = [
  { label: "Gas (MQ2)", color: tokens.gasColor, points: "0,45 15,10 30,50 45,5 60,40 75,15 100,20" },
  { label: "CO2 (MQ7)", color: tokens.co2Color, points: "0,52 15,38 30,40 45,25 60,30 75,32 100,22" },
  { label: "Humidity", color: tokens.humidityColor, points: "0,48 15,44 30,30 45,32 60,18 75,22 100,15" },
];

// Matches Figma: Rectangle 4, 366x249, bg #1C1F24, radius 10, grid-line texture
export default function EnvironmentCard() {
  return (
    <div
      className="rounded-[10px] p-5 w-full h-full flex flex-col transition-all duration-200 ease-out env-card"
      style={{ backgroundColor: tokens.bgSurface, border: `1px solid ${tokens.border}`, minHeight: 249 }}
    >
      <style>{`
        .env-card:hover {
          border-color: ${tokens.navy} !important;
          box-shadow: 0 0 20px rgba(124, 147, 216, 0.06);
        }
      `}</style>
      {/* Figma Frame 22: icon + text group, gap 7px */}
      <div className="flex items-start gap-[7px]">
        <svg width="18" height="18" viewBox="0 0 24 24" fill={tokens.textPrimary} className="shrink-0 mt-0.5">
          <path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.25S2 11.5 2 13.5s1.75 3.75 1.75 3.75"/>
        </svg>
        <div className="flex flex-col gap-[7px]">
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 15, lineHeight: "19px", color: tokens.textPrimary }}>
            Environment
          </p>
          <p style={{ fontFamily: fontSora, fontWeight: 600, fontSize: 10, lineHeight: "13px", color: tokens.textTertiary }}>
            Last updated 30 sec ago
          </p>
        </div>
      </div>

      {/* Grid-paper background behind the graph, matches the Line 15-39 grid in Figma */}
      <div
        className="flex-1 mt-3 rounded-md relative overflow-hidden"
        style={{
          backgroundImage: `
            repeating-linear-gradient(to right, ${tokens.gridLine} 0, ${tokens.gridLine} 1px, transparent 1px, transparent 12.5%),
            repeating-linear-gradient(to bottom, ${tokens.gridLine} 0, ${tokens.gridLine} 1px, transparent 1px, transparent 25%)
          `,
        }}
      >
        <svg viewBox="0 0 100 60" preserveAspectRatio="none" className="w-full h-full">
          {metrics.map((m) => (
            <polyline
              key={m.label}
              points={m.points}
              fill="none"
              stroke={m.color}
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </svg>
      </div>

      <div className="flex justify-center gap-[27px] mt-3">
        {metrics.map((m) => (
          <div key={m.label} className="flex flex-col items-center gap-[3px] w-[66px]">
            <div className="flex items-center w-full">
              <span className="w-[5px] h-[5px] rounded-full shrink-0" style={{ backgroundColor: m.color }} />
              <span className="flex-1 h-[1.5px]" style={{ backgroundColor: m.color }} />
            </div>
            <span
              style={{
                fontFamily: fontSora,
                fontWeight: 400,
                fontSize: 7,
                lineHeight: "9px",
                textAlign: "center",
                color: tokens.textTertiary,
              }}
            >
              {m.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
