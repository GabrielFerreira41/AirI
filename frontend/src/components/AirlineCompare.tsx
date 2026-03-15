"use client";

import type { AirlineResult } from "@/lib/types";

interface Props {
  airlines:      AirlineResult[];
  selectedCode:  string;
  threshold:     number;
}

const AIRLINE_FLAGS: Record<string, string> = {
  AC: "🍁", WS: "🌤", PD: "🔵", F8: "🟠",
  UA: "🔷", DL: "🔺", AA: "🦅", WN: "❤️",
};

export default function AirlineCompare({ airlines, selectedCode, threshold }: Props) {
  if (!airlines.length) return null;

  const maxProb = Math.max(...airlines.map(a => a.probability), threshold + 0.01);

  return (
    <div className="ac-wrap">
      <div className="ac-header">
        <span className="ac-title">Comparaison compagnies</span>
        <span className="ac-subtitle">{airlines[0] && `Meilleur : ${airlines[0].name}`}</span>
      </div>

      <div className="ac-list">
        {airlines.map((a, i) => {
          const pct      = Math.round(a.probability * 100);
          const barW     = (a.probability / maxProb) * 100;
          const isFirst  = i === 0;
          const isSelected = a.code === selectedCode;
          const color    = a.is_delayed ? "var(--red)" : "var(--green)";

          return (
            <div key={a.code}
              className={`ac-row${isSelected ? " ac-row--selected" : ""}${isFirst ? " ac-row--best" : ""}`}>

              <div className="ac-airline">
                <span className="ac-flag">{AIRLINE_FLAGS[a.code] ?? "✈"}</span>
                <div className="ac-names">
                  <span className="ac-code">{a.code}</span>
                  <span className="ac-name">{a.name}</span>
                </div>
              </div>

              <div className="ac-bar-wrap">
                <div className="ac-bar" style={{ width: `${barW}%`, background: color }} />
                <div className="ac-threshold" style={{ left: `${(threshold / maxProb) * 100}%` }} />
              </div>

              <div className="ac-right">
                <span className="ac-pct" style={{ color }}>{pct}%</span>
                {a.is_delayed && a.delay_minutes > 0 && (
                  <span className="ac-delay">+{Math.round(a.delay_minutes)} min</span>
                )}
              </div>

              {isFirst && <span className="ac-badge-best">✓</span>}
              {isSelected && !isFirst && <span className="ac-badge-sel">◀</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
