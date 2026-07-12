"use client";

import { tokens, fontSora } from "./tokens";

// Placeholder for the GPS map — swap for your actual map component
// (Mapbox/Leaflet/Google Maps) once BE starts sending lat/long.
export default function MapPlaceholder() {
  return (
    <div
      className="rounded-[10px] w-full h-full flex flex-col relative overflow-hidden transition-all duration-200 ease-out map-card min-h-[240px] lg:min-h-[380px]"
      style={{ backgroundColor: tokens.bgSurface, border: `1px solid ${tokens.border}` }}
    >
      <style>{`
        .map-card:hover {
          border-color: ${tokens.navy} !important;
          box-shadow: 0 0 20px rgba(124, 147, 216, 0.06);
        }
        .map-card:hover .map-dot {
          transform: scale(1.6);
          opacity: 0.8;
        }
      `}</style>
      <button
        aria-label="Expand map"
        className="absolute top-3 right-3 w-8 h-8 rounded-full flex items-center justify-center"
        style={{ backgroundColor: tokens.surfaceInverse }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#121417" strokeWidth="2" strokeLinecap="round">
          <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
        </svg>
      </button>

      <div className="flex-1 flex items-center justify-center">
        <span className="w-2.5 h-2.5 rounded-full map-dot transition-transform duration-300" style={{ backgroundColor: tokens.textTertiary }} />
      </div>

      <p
        className="absolute bottom-3 left-4"
        style={{ fontFamily: fontSora, fontWeight: 500, fontSize: 11, color: tokens.textTertiary }}
      >
        GPS map area
      </p>
    </div>
  );
}
