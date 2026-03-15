"use client";

import type { TimelinePoint } from "@/lib/types";

interface Props {
  points:      TimelinePoint[];
  threshold:   number;
  bestHours:   number[];
  worstHours:  number[];
  currentHour: number;
}

const W = 268, H = 96;
const PL = 6, PR = 6, PT = 18, PB = 24;
const CW = W - PL - PR;   // 256
const CH = H - PT - PB;   // 54

function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }

export default function TimelineChart({ points, threshold, bestHours, worstHours, currentHour }: Props) {
  if (points.length < 24) return null;

  const xs = points.map((_, i) => PL + (i / 23) * CW);
  const yP = (p: number) => PT + CH - p * CH;          // probability → y
  const thY = yP(threshold);

  // ── Zones horaires (fond) ───────────────────────────────────────
  const zones = [
    { from: 0,  to: 6,  label: "nuit",    fill: "rgba(15,20,50,0.06)"  },
    { from: 6,  to: 12, label: "matin",   fill: "rgba(255,200,0,0.04)" },
    { from: 12, to: 18, label: "après",   fill: "rgba(255,200,0,0.04)" },
    { from: 18, to: 23, label: "soir",    fill: "rgba(15,20,50,0.06)"  },
  ];

  // ── Aire sous la courbe ──────────────────────────────────────────
  const areaAbove = points.map((p, i) => {
    const prob = Math.min(p.probability, 1);
    const y    = yP(prob);
    return `${i === 0 ? "M" : "L"}${xs[i].toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + ` L${xs[23].toFixed(1)},${(PT + CH).toFixed(1)} L${xs[0].toFixed(1)},${(PT + CH).toFixed(1)} Z`;

  // ── Ligne de probabilité ─────────────────────────────────────────
  const linePath = points.map((p, i) => {
    const y = yP(Math.min(p.probability, 1));
    return `${i === 0 ? "M" : "L"}${xs[i].toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  // ── Labels heures ────────────────────────────────────────────────
  const showLabel = (h: number) => h % 6 === 0 || h === currentHour;

  return (
    <div className="tl-wrap">
      <div className="tl-header">
        <span className="tl-title">Meilleur horaire de départ</span>
        <div className="tl-legend">
          <span className="tl-leg tl-leg--best">✓ Optimal</span>
          <span className="tl-leg tl-leg--worst">⚠ Risqué</span>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ height: H, display: "block" }}>

        {/* Zones horaires */}
        {zones.map((z, i) => (
          <rect
            key={i}
            x={xs[z.from]}
            y={PT}
            width={xs[Math.min(z.to, 23)] - xs[z.from]}
            height={CH}
            fill={z.fill}
          />
        ))}

        {/* Grille horizontale */}
        {[0.25, 0.5, 0.75].map((f, i) => (
          <line key={i}
            x1={PL} y1={yP(f)} x2={W - PR} y2={yP(f)}
            stroke="#e8eaed" strokeWidth={0.5}
          />
        ))}

        {/* Aire de la courbe */}
        <path d={areaAbove} fill="url(#tlGradient)" opacity={0.35} />
        <defs>
          <linearGradient id="tlGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#d93025" />
            <stop offset="50%"  stopColor="#f9ab00" />
            <stop offset="100%" stopColor="#1e8e3e" />
          </linearGradient>
        </defs>

        {/* Ligne de seuil */}
        <line
          x1={PL} y1={thY} x2={W - PR} y2={thY}
          stroke="#f9ab00" strokeWidth={1} strokeDasharray="4,3"
        />
        <text x={W - PR - 2} y={thY - 3} textAnchor="end"
          fontSize={7} fill="#f9ab00" fontFamily="Roboto Mono, monospace" fontWeight="600">
          seuil {Math.round(threshold * 100)}%
        </text>

        {/* Ligne de probabilité */}
        <path d={linePath} fill="none" stroke="#1a73e8" strokeWidth={1.5}
          strokeLinejoin="round" strokeLinecap="round" />

        {/* Points best / worst / current */}
        {points.map((p, i) => {
          const isBest    = bestHours.includes(i);
          const isWorst   = worstHours.includes(i);
          const isCurrent = i === currentHour;
          if (!isBest && !isWorst && !isCurrent) return null;
          const cx = xs[i];
          const cy = yP(p.probability);
          const fill = isCurrent ? "#1a73e8" : isBest ? "#1e8e3e" : "#d93025";
          return (
            <circle key={i} cx={cx} cy={cy}
              r={isCurrent ? 4 : 3}
              fill={isCurrent ? "#1a73e8" : "white"}
              stroke={fill} strokeWidth={1.5}
            />
          );
        })}

        {/* Marqueur heure sélectionnée */}
        <line
          x1={xs[currentHour]} y1={PT - 4}
          x2={xs[currentHour]} y2={PT + CH}
          stroke="#1a73e8" strokeWidth={1} strokeDasharray="3,2"
        />
        <text x={xs[currentHour]} y={PT - 6}
          textAnchor={currentHour > 18 ? "end" : "middle"}
          fontSize={7.5} fill="#1a73e8"
          fontFamily="Roboto Mono, monospace" fontWeight="700">
          ✈ {currentHour}h
        </text>

        {/* Badges best hours */}
        {bestHours.map(h => (
          <text key={h} x={xs[h]} y={yP(points[h].probability) - 6}
            textAnchor="middle" fontSize={7} fill="#1e8e3e"
            fontFamily="Roboto Mono, monospace">
            {h}h
          </text>
        ))}

        {/* Ligne de base */}
        <line x1={PL} y1={PT + CH} x2={W - PR} y2={PT + CH}
          stroke="#dadce0" strokeWidth={1} />

        {/* Labels heures X */}
        {points.map((_, i) => {
          if (!showLabel(i)) return null;
          return (
            <text key={i} x={xs[i]} y={H - 6}
              textAnchor="middle" fontSize={8}
              fill={i === currentHour ? "#1a73e8" : "#9aa0a6"}
              fontWeight={i === currentHour ? "700" : "400"}
              fontFamily="Roboto Mono, monospace">
              {i}h
            </text>
          );
        })}
      </svg>

      {/* Résumé texte */}
      <div className="tl-summary">
        <span className="tl-sum-best">
          ✓ Meilleurs créneaux : {bestHours.map(h => `${h}h`).join(", ")}
        </span>
        <span className="tl-sum-worst">
          ⚠ Éviter : {worstHours.map(h => `${h}h`).join(", ")}
        </span>
      </div>
    </div>
  );
}
