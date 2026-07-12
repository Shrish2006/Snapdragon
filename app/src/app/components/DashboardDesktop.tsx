"use client";

import { useMemo } from "react";
import StatusStrip from "./StatusStrip";
import HeartRateCard from "./HeartRateCard";
import EnvironmentCard from "./EnvironmentCard";
import TemperatureCard from "./TemperatureCard";
import MotionStatusCard from "./MotionStatusCard";
import MapPlaceholder from "./MapPlaceholder";
import AlertsCard from "./AlertsCard";
import { tokens } from "./tokens";
import { useHelmets } from "@/hooks/useHelmets";
import { HelmetLiveProvider } from "@/hooks/HelmetLiveProvider";
import {
  useAirQualityStatus,
  useAlerts,
  useAmbientTemperature,
  useEnvironmentTrend,
  useGatewayHealthStatus,
  useMotionStatus,
  useSoundStatus,
} from "@/hooks/useSensorViews";
import { getDefaultHelmetId } from "@/lib/api";

// Layout: mobile stack (Map → Status → HeartRate → Environment → Motion → Temperature → Alerts)
// Desktop (lg+): 60:40 split — left (cards), right (map only)
export default function DashboardDesktop() {
  const { helmets } = useHelmets();

  const selectedHelmetId = useMemo(() => {
    const override = getDefaultHelmetId();
    if (override) return override;
    const online = helmets.find((helmet) => helmet.status === "online");
    return (online ?? helmets[0])?.helmet_id ?? null;
  }, [helmets]);

  return (
    <HelmetLiveProvider helmetId={selectedHelmetId}>
      <DashboardBody />
    </HelmetLiveProvider>
  );
}

/** Layout unchanged from the original static markup — this component
 * only adds data wiring via the per-card hooks in `@/hooks/useSensorViews`,
 * fed by the `HelmetLiveProvider` this file renders above. */
function DashboardBody() {
  const sound = useSoundStatus();
  const airQuality = useAirQualityStatus();
  const environment = useEnvironmentTrend();
  const motion = useMotionStatus();
  const temperature = useAmbientTemperature();
  const alerts = useAlerts();
  const gatewayHealth = useGatewayHealthStatus();

  return (
    <div className="min-h-screen w-full p-4 lg:p-8" style={{ backgroundColor: tokens.bgBase }}>
      <div className="max-w-[1400px] mx-auto">
        {/* ── MOBILE / TABLET STACK (< lg) ── */}
        <div className="flex flex-col gap-4 lg:hidden">
          <MapPlaceholder />
          <StatusStrip sound={sound.view} airQuality={airQuality.view} gatewayHealth={gatewayHealth} />
          <HeartRateCard />
          <EnvironmentCard {...environment} />
          <MotionStatusCard state={motion.state} lastUpdated={motion.lastUpdated} />
          <TemperatureCard ambientTemp={temperature.ambientTemp} lastUpdated={temperature.lastUpdated} />
          <AlertsCard {...alerts} />
        </div>

        {/* ── DESKTOP GRID (lg+) ── */}
        <div className="hidden lg:grid gap-4" style={{ gridTemplateColumns: "3fr 2fr" }}>
          {/* LEFT SECTION */}
          <div className="flex flex-col gap-4">
            <StatusStrip sound={sound.view} airQuality={airQuality.view} gatewayHealth={gatewayHealth} />

            {/* Row: Heart Rate fills available space | Motion Status + Temperature stacked (256px) */}
            <div className="flex gap-4 items-start">
              <div className="flex-1">
                <HeartRateCard />
              </div>
              <div className="flex flex-col gap-4 shrink-0" style={{ width: 256 }}>
                <MotionStatusCard state={motion.state} lastUpdated={motion.lastUpdated} />
                <TemperatureCard ambientTemp={temperature.ambientTemp} lastUpdated={temperature.lastUpdated} />
              </div>
            </div>

            {/* Environment spans full left width below the row */}
            <EnvironmentCard {...environment} />
            <AlertsCard {...alerts} />
          </div>

          {/* RIGHT SECTION: Map only */}
          <MapPlaceholder />
        </div>
      </div>
    </div>
  );
}
