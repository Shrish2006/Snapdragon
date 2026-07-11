"use client";

import StatusStrip from "./StatusStrip";
import HeartRateCard from "./HeartRateCard";
import EnvironmentCard from "./EnvironmentCard";
import TemperatureCard from "./TemperatureCard";
import MotionStatusCard from "./MotionStatusCard";
import MapPlaceholder from "./MapPlaceholder";
import { tokens } from "./tokens";

// Layout: mobile stack (Map → Status → HeartRate → Environment → Motion → Temperature)
// Desktop (lg+): 60:40 split — left (cards), right (map only)
export default function DashboardDesktop() {
  return (
    <div className="min-h-screen w-full p-4 lg:p-8" style={{ backgroundColor: tokens.bgBase }}>
      <div className="max-w-[1400px] mx-auto">
        {/* ── MOBILE / TABLET STACK (< lg) ── */}
        <div className="flex flex-col gap-4 lg:hidden">
          <MapPlaceholder />
          <StatusStrip />
          <HeartRateCard />
          <EnvironmentCard />
          <MotionStatusCard />
          <TemperatureCard />
        </div>

        {/* ── DESKTOP GRID (lg+) ── */}
        <div className="hidden lg:grid gap-4" style={{ gridTemplateColumns: "3fr 2fr" }}>
          {/* LEFT SECTION */}
          <div className="flex flex-col gap-4">
            <StatusStrip />

            {/* Row: Heart Rate fills available space | Motion Status + Temperature stacked (256px) */}
            <div className="flex gap-4 items-start">
              <div className="flex-1">
                <HeartRateCard />
              </div>
              <div className="flex flex-col gap-4 shrink-0" style={{ width: 256 }}>
                <MotionStatusCard />
                <TemperatureCard />
              </div>
            </div>

            {/* Environment spans full left width below the row */}
            <EnvironmentCard />
          </div>

          {/* RIGHT SECTION: Map only */}
          <MapPlaceholder />
        </div>
      </div>
    </div>
  );
}
