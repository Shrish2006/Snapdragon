"use client";

// Per-card view-model hooks. Each wraps `useHelmetLive()` + the pure
// mappers in `lib/sensors/normalize.ts` so components call one hook and
// receive exactly the props their existing UI already expects — no
// component ever reads `latest_readings` or a raw `SensorReading` itself.

import { useHelmetLive } from "./HelmetLiveProvider";
import { useServiceStatus } from "./useServiceStatus";
import type { AnalogGasReading, EnvironmentReading, ImuReading, SoundLevelReading } from "@/lib/api";
import {
  describeEvent,
  formatRelativeTime,
  normalizeAirQuality,
  normalizeMlFallEvent,
  normalizeMotion,
  normalizeSound,
  pickReading,
  summarizeServiceHealth,
  toSvgPolylinePoints,
  type AirQualityView,
  type MotionState,
  type SoundReadingView,
} from "@/lib/sensors/normalize";
import type { SensorStatus } from "@/app/components/tokens";

const GAS_ADC_MAX = 1023;

export interface SoundCardData {
  view: SoundReadingView | null;
  lastUpdated: string;
}

export function useSoundStatus(): SoundCardData {
  const { helmet } = useHelmetLive();
  const reading = helmet ? pickReading<SoundLevelReading>(helmet.latest_readings, "sound_level") : undefined;
  const capturedAt = helmet?.latest_readings.sound_level?.captured_at ?? null;
  return { view: normalizeSound(reading), lastUpdated: formatRelativeTime(capturedAt) };
}

export interface AirQualityCardData {
  view: AirQualityView | null;
  lastUpdated: string;
}

export function useAirQualityStatus(): AirQualityCardData {
  const { helmet } = useHelmetLive();
  const gas = helmet ? pickReading<AnalogGasReading>(helmet.latest_readings, "gas_lpg") : undefined;
  const co = helmet ? pickReading<AnalogGasReading>(helmet.latest_readings, "carbon_monoxide") : undefined;
  const capturedAt = helmet?.latest_readings.gas_lpg?.captured_at ?? helmet?.latest_readings.carbon_monoxide?.captured_at ?? null;
  return { view: normalizeAirQuality(gas, co), lastUpdated: formatRelativeTime(capturedAt) };
}

export interface MotionCardData {
  state: MotionState | null;
  lastUpdated: string;
}

/** IMU-derived motion, overridden by a real `ml.result` fall signal from
 * the fall-detection service the moment that service starts emitting
 * one (see `normalizeMlFallEvent`'s docstring). */
export function useMotionStatus(): MotionCardData {
  const { helmet, lastMlFallSignal } = useHelmetLive();
  const reading = helmet ? pickReading<ImuReading>(helmet.latest_readings, "imu") : undefined;
  const capturedAt = helmet?.latest_readings.imu?.captured_at ?? null;

  const mlState = lastMlFallSignal ? normalizeMlFallEvent(lastMlFallSignal.service, lastMlFallSignal.payload) : null;
  const isMlSignalNewer = lastMlFallSignal && capturedAt && new Date(lastMlFallSignal.occurredAt).getTime() > new Date(capturedAt).getTime();

  const state = isMlSignalNewer && mlState ? mlState : normalizeMotion(reading);
  const lastUpdated = isMlSignalNewer ? formatRelativeTime(lastMlFallSignal!.occurredAt) : formatRelativeTime(capturedAt);

  return { state, lastUpdated };
}

export interface TemperatureCardData {
  ambientTemp: number | null;
  lastUpdated: string;
}

export function useAmbientTemperature(): TemperatureCardData {
  const { helmet } = useHelmetLive();
  const reading = helmet ? pickReading<EnvironmentReading>(helmet.latest_readings, "environment") : undefined;
  const capturedAt = helmet?.latest_readings.environment?.captured_at ?? null;
  return {
    ambientTemp: reading ? Math.round(reading.temperature_c * 10) / 10 : null,
    lastUpdated: formatRelativeTime(capturedAt),
  };
}

export interface EnvironmentCardData {
  gasPoints: string;
  coPoints: string;
  humidityPoints: string;
  lastUpdated: string;
}

export function useEnvironmentTrend(): EnvironmentCardData {
  const { helmet, environmentHistory } = useHelmetLive();
  const capturedAt = helmet?.latest_readings.environment?.captured_at ?? environmentHistory.at(-1)?.capturedAt ?? null;

  const gasValues = environmentHistory.map((point) => point.gasAdcRaw).filter((value): value is number => value !== null);
  const coValues = environmentHistory.map((point) => point.coAdcRaw).filter((value): value is number => value !== null);
  const humidityValues = environmentHistory.map((point) => point.humidityPct).filter((value): value is number => value !== null);

  return {
    gasPoints: toSvgPolylinePoints(gasValues, GAS_ADC_MAX),
    coPoints: toSvgPolylinePoints(coValues, GAS_ADC_MAX),
    humidityPoints: toSvgPolylinePoints(humidityValues, 100),
    lastUpdated: formatRelativeTime(capturedAt),
  };
}

export interface AlertsCardData {
  alerts: { id: string; label: string; status: SensorStatus; timestamp: string }[];
  lastUpdated: string;
}

export function useAlerts(): AlertsCardData {
  const { alerts } = useHelmetLive();
  return {
    alerts: alerts.map((event) => {
      const described = describeEvent(event);
      return { id: described.id, label: described.label, status: described.status, timestamp: formatRelativeTime(described.occurredAt) };
    }),
    lastUpdated: formatRelativeTime(alerts[0]?.occurred_at ?? null),
  };
}

export interface GatewayHealthPillData {
  value: string;
  status: SensorStatus;
}

export function useGatewayHealthStatus(): GatewayHealthPillData {
  const { status } = useServiceStatus();
  return summarizeServiceHealth(status);
}
