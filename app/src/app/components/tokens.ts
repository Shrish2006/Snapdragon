// Shared design tokens — matches final Figma dev-mode export.
// Load fonts in your root layout.tsx:
//   import { Sora, DM_Mono } from "next/font/google";
//   const sora = Sora({ subsets: ["latin"], variable: "--font-sora" });
//   const dmMono = DM_Mono({ subsets: ["latin"], weight: ["400","500"], variable: "--font-mono" });

export const tokens = {
  bgBase: "#121417",
  bgSurface: "#1C1F24",
  bgElevated: "#24272D",

  textPrimary: "#F2F1EF",
  textSecondary: "#9497A0",
  textTertiary: "#6E7177",

  navy: "#7C93D8",
  navyDim: "#4A5C94",

  amber: "#F0A030",
  red: "#F2666B",
  green: "#5FBF7F",

  border: "#2C2F34",
  borderLight: "#3A3D42",
  gridLine: "#2A2D34",
  gridLineStrong: "#393D45",

  // Heart rate card sits on the inverse (light) surface — its own text scale
  surfaceInverse: "#F2F1EF",
  surfaceInverseTitle: "#555555",
  surfaceInverseSubtitle: "#B0B0B0",
  ecgLine: "#FB353D",
  bpmText: "#000000",
  bpmStatusNormal: "#45895C",

  // Environment graph line colors — fixed per metric, not status-driven
  gasColor: "#436FF3",
  co2Color: "#F2F1EF",
  humidityColor: "#819DF2",
} as const;

export type SensorStatus = "normal" | "warning" | "danger";

export const statusColor = (status: SensorStatus) => {
  if (status === "danger") return tokens.red;
  if (status === "warning") return tokens.amber;
  return tokens.green;
};

export const fontSora = "var(--font-sora), sans-serif";
export const fontMono = "var(--font-mono), monospace";
