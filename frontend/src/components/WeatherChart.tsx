"use client";

import type { HourlyPoint } from "@/lib/types";

interface Props {
  hours: HourlyPoint[];
  iata:  string;
}

const W = 268, H = 88;
const PL = 6, PR = 6, PT = 16, PB = 22;
const CW = W - PL - PR;  // 256
const CH = H - PT - PB;  // 50

export default function WeatherChart({ hours, iata }: Props) {
  if (hours.length < 2) return null;

  const n  = hours.length;
  const xs = hours.map((_, i) => PL + (i / (n - 1)) * CW);

  // ── Température (ligne rouge) ──────────────────────────
  const temps  = hours.map(h => h.temperature);
  const minT   = Math.min(...temps);
  const maxT   = Math.max(...temps);
  const rangeT = Math.max(maxT - minT, 2);
  const yT = (t: number) => PT + CH - ((t - minT) / rangeT) * CH;

  const tempPath = hours
    .map((h, i) => `${i === 0 ? "M" : "L"}${xs[i].toFixed(1)},${yT(h.temperature).toFixed(1)}`)
    .join(" ");

  // ── Vent (ligne grise en arrière-plan) ────────────────
  const winds  = hours.map(h => h.wind_kmh);
  const minW   = Math.min(...winds);
  const maxW   = Math.max(...winds);
  const rangeW = Math.max(maxW - minW, 5);
  const yW = (w: number) => PT + CH - ((w - minW) / rangeW) * CH;

  const windPath = hours
    .map((h, i) => `${i === 0 ? "M" : "L"}${xs[i].toFixed(1)},${yW(h.wind_kmh).toFixed(1)}`)
    .join(" ");

  // ── Précipitations (barres bleues en bas) ─────────────
  const maxP  = Math.max(...hours.map(h => h.precip_mm), 0.5);
  const BAR_H = 12;
  const barW  = Math.max((CW / n) * 0.55, 3);

  // ── Index départ ──────────────────────────────────────
  const depIdx = hours.findIndex(h => h.is_departure);

  // Labels : premier, dernier, départ, tous les 3
  const showLabel = (i: number) =>
    i === 0 || i === n - 1 || hours[i].is_departure || i % 3 === 0;

  return (
    <div className="wxchart-wrap">
      <div className="wxchart-header">
        <span className="wxchart-title">Météo 12h · {iata}</span>
        <div className="wxchart-legend">
          <span className="wxchart-leg wxchart-leg--temp">temp.</span>
          <span className="wxchart-leg wxchart-leg--wind">vent</span>
          <span className="wxchart-leg wxchart-leg--rain">précip.</span>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ height: H, display: "block" }}
        aria-label={`Météo horaire à ${iata}`}
      >
        {/* Grille horizontale légère */}
        {[0.25, 0.5, 0.75].map((f, i) => (
          <line
            key={i}
            x1={PL} y1={PT + CH * (1 - f)}
            x2={W - PR} y2={PT + CH * (1 - f)}
            stroke="#e8eaed" strokeWidth={0.5}
          />
        ))}

        {/* Ligne de base */}
        <line x1={PL} y1={PT + CH} x2={W - PR} y2={PT + CH} stroke="#dadce0" strokeWidth={1} />

        {/* Barres précipitations */}
        {hours.map((h, i) => {
          if (h.precip_mm < 0.05) return null;
          const bh = (h.precip_mm / maxP) * BAR_H;
          return (
            <rect
              key={i}
              x={xs[i] - barW / 2}
              y={PT + CH - bh}
              width={barW}
              height={bh}
              fill={h.is_departure ? "rgba(26,115,232,0.5)" : "rgba(26,115,232,0.22)"}
              rx={1.5}
            />
          );
        })}

        {/* Ligne vent */}
        <path d={windPath} fill="none" stroke="#bdc1c6" strokeWidth={1} strokeLinejoin="round" strokeDasharray="3,2" />

        {/* Ligne température */}
        <path d={tempPath} fill="none" stroke="#d93025" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />

        {/* Points température */}
        {hours.map((h, i) => (
          <circle
            key={i}
            cx={xs[i]}
            cy={yT(h.temperature)}
            r={h.is_departure ? 3.5 : 2}
            fill={h.is_departure ? "#d93025" : "#fff"}
            stroke="#d93025"
            strokeWidth={1.5}
          />
        ))}

        {/* Marqueur départ */}
        {depIdx >= 0 && (
          <>
            <line
              x1={xs[depIdx]} y1={PT - 10}
              x2={xs[depIdx]} y2={PT + CH}
              stroke="#1a73e8" strokeWidth={1} strokeDasharray="3,2"
            />
            <text
              x={xs[depIdx]} y={PT - 12}
              textAnchor="middle"
              fontSize={7.5} fontWeight="700"
              fill="#1a73e8" fontFamily="Roboto Mono, monospace"
            >
              ✈
            </text>
          </>
        )}

        {/* Valeur temp au départ */}
        {depIdx >= 0 && (
          <text
            x={xs[depIdx] + (xs[depIdx] > W / 2 ? -5 : 5)}
            y={yT(hours[depIdx].temperature) - 5}
            textAnchor={xs[depIdx] > W / 2 ? "end" : "start"}
            fontSize={8} fill="#d93025"
            fontFamily="Roboto Mono, monospace" fontWeight="600"
          >
            {hours[depIdx].temperature > 0 ? "+" : ""}{hours[depIdx].temperature.toFixed(0)}°
          </text>
        )}

        {/* Labels heures */}
        {hours.map((h, i) => {
          if (!showLabel(i)) return null;
          return (
            <text
              key={i}
              x={xs[i]} y={H - 5}
              textAnchor="middle"
              fontSize={8}
              fill={h.is_departure ? "#1a73e8" : "#9aa0a6"}
              fontWeight={h.is_departure ? "700" : "400"}
              fontFamily="Roboto Mono, monospace"
            >
              {h.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
