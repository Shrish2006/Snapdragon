"use client";

import { tokens, fontSora, fontMono } from "./tokens";

interface HeartRateCardProps {
  bpm?: number;
  statusLabel?: string;
  lastUpdated?: string;
}

// Matches Figma: Rectangle 3, 366x249, bg #F2F1EF, radius 10
export default function HeartRateCard({
  bpm = 92,
  statusLabel = "Normal",
  lastUpdated = "2 min ago",
}: HeartRateCardProps) {
  const duration = Math.max(0.6, 60 / bpm);

  return (
    <div
      className="rounded-[10px] p-5 w-full h-full flex flex-col transition-all duration-200 ease-out hr-card"
      style={{ backgroundColor: tokens.surfaceInverse, minHeight: 249 }}>
      <style>{`
        .hr-card:hover {
          box-shadow: 0 4px 24px rgba(0,0,0,0.12);
          transform: translateY(-1px);
        }
      `}</style>
      {/* Figma Frame 21: icon + text group, gap 5px */}
      <div className="flex items-start gap-[5px]">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="shrink-0 mt-0.5">
          <path d="M7 12h2l1-5 2 10 1-5h3" stroke={tokens.surfaceInverseTitle} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" fill={tokens.surfaceInverseTitle}/>
        </svg>
        <div className="flex flex-col gap-[7px]">
          <p
            style={{
              fontFamily: fontSora,
              fontWeight: 600,
              fontSize: 15,
              lineHeight: "19px",
              color: tokens.surfaceInverseTitle,
            }}
          >
            Heart rate
          </p>
          <p
            style={{
              fontFamily: fontSora,
              fontWeight: 600,
              fontSize: 10,
              lineHeight: "13px",
              color: tokens.surfaceInverseSubtitle,
            }}
          >
            Last updated {lastUpdated}
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center my-2">
        <svg viewBox="0 0 226 70" className="w-[80%] h-auto" preserveAspectRatio="xMidYMid meet">
          <polyline
            points="0,35 40,35 55,10 65,60 75,5 85,55 95,35 130,35 145,10 155,60 165,5 175,55 185,35 226,35"
            fill="none"
            stroke={tokens.ecgLine}
            strokeWidth="4.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{
              strokeDasharray: 700,
              strokeDashoffset: 700,
              animation: `hr-ecg-draw ${duration * 3}s linear infinite`,
            }}
          />
        </svg>
      </div>

      <div className="flex flex-col items-center gap-1">
        <span style={{ fontFamily: fontMono, fontWeight: 500, fontSize: 15, lineHeight: "20px", color: tokens.bpmText }}>
          {bpm} BPM
        </span>
        <span
          style={{
            fontFamily: fontMono,
            fontWeight: 500,
            fontSize: 10,
            lineHeight: "13px",
            textAlign: "center",
            color: tokens.bpmStatusNormal,
          }}
        >
          {statusLabel}
        </span>
      </div>

      <style>{`
        @keyframes hr-ecg-draw {
          0% { stroke-dashoffset: 700; }
          100% { stroke-dashoffset: 0; }
        }
      `}</style>
    </div>
  );
}
