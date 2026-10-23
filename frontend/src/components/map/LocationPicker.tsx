"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { toScreen, unproject, type LatLon } from "@/lib/map";
import { useMapView } from "@/lib/useMapView";

const W = 900;
const H = 520;
// the map opens on Chandigarh, wide enough to show most sectors
const START: LatLon[] = [
  { lat: 30.715, lon: 76.755 },
  { lat: 30.755, lon: 76.805 },
];

export interface PickerHandle {
  /** Move the map to a place (for example the person's GPS fix) at street level. */
  flyTo: (place: LatLon) => void;
}

interface Props {
  value: LatLon | null;
  onChange: (place: LatLon) => void;
  /** Metres of uncertainty around the value, drawn as a soft circle (from GPS). */
  accuracy?: number | null;
}

export const LocationPicker = forwardRef<PickerHandle, Props>(function LocationPicker({ value, onChange, accuracy }, ref) {
  const svg = useRef<SVGSVGElement>(null);
  const [tilesFailed, setTilesFailed] = useState(false);
  const map = useMapView(START, W, H, svg, 0.7);
  useImperativeHandle(ref, () => ({ flyTo: (place) => map.centreOn(place, 17) }));

  const place = (point: { x: number; y: number }) => {
    const world = { x: map.view.cx + point.x - W / 2, y: map.view.cy + point.y - H / 2 };
    const next = unproject(world.x, world.y, map.view.zoom);
    onChange(next);
    // the first tap lands on a wide map, so move in to street level and let the person fine-tune
    if (!value) map.centreOn(next, 16);
  };

  const pin = value ? toScreen(map.view, W, H, value) : null;
  const metersPerPixel = value ? (156543.03392 * Math.cos((value.lat * Math.PI) / 180)) / 2 ** map.view.zoom : 1;
  const radius = accuracy && value ? Math.max(10, accuracy / metersPerPixel) : 0;

  return (
    <div className="picker">
      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${H}`}
        role="application"
        aria-label="Map. Click or tap to place the pin where you saw the waste."
        data-dragging={map.dragging ? "" : undefined}
        {...map.handlers(place)}
      >
        <defs>
          <pattern id="lgrid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M50 0H0V50" fill="none" stroke="oklch(0.9 0.008 250)" strokeWidth="1" />
          </pattern>
          <filter id="pin-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="3" stdDeviation="3" floodColor="#14213d" floodOpacity="0.45" />
          </filter>
        </defs>
        <rect width={W} height={H} fill="oklch(0.965 0.006 250)" />
        <rect width={W} height={H} fill="url(#lgrid)" />
        {!tilesFailed && map.tiles.map((t) => <image key={t.key} className="map-tile" href={t.src} x={t.x} y={t.y} width={256} height={256} onError={() => setTilesFailed(true)} />)}
        <rect width={W} height={H} fill="oklch(0.2 0.03 258)" opacity="0.06" />

        {pin && (
          <g transform={`translate(${pin.x} ${pin.y})`}>
            {radius > 0 && <circle r={radius} className="accuracy" />}
            <g className="dropped" filter="url(#pin-glow)">
              <path d="M0 0 C-10 -14 -18 -22 -18 -32 A18 18 0 1 1 18 -32 C18 -22 10 -14 0 0Z" fill="url(#pin-fill)" stroke="#fff" strokeWidth="2.5" />
              <circle cy="-32" r="7" fill="#fff" />
            </g>
          </g>
        )}
        <defs>
          <linearGradient id="pin-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#e2621f" />
            <stop offset="1" stopColor="#a63500" />
          </linearGradient>
        </defs>
      </svg>

      <div className="sightings-zoom">
        <button type="button" className="btn" aria-label="Zoom in" onClick={map.zoomIn}>
          +
        </button>
        <button type="button" className="btn" aria-label="Zoom out" onClick={map.zoomOut}>
          −
        </button>
      </div>
      <span className="routemap-credit">{tilesFailed ? "Street map unavailable offline" : "© OpenStreetMap contributors"}</span>
      {!value && <span className="picker-hint">Tap the map to drop a pin, or use your location</span>}
    </div>
  );
});
