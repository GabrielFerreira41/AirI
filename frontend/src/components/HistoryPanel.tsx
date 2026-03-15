"use client";

import type { HistoryEntry } from "@/lib/types";

interface Props {
  history:  HistoryEntry[];
  onSelect: (entry: HistoryEntry) => void;
  onClear:  () => void;
}

function formatDt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("fr-CA", { month: "short", day: "numeric" })
       + " · " + d.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export default function HistoryPanel({ history, onSelect, onClear }: Props) {
  if (!history.length) return null;

  return (
    <div className="hist-wrap">
      <div className="hist-header">
        <span className="hist-title">Recherches récentes</span>
        <button className="hist-clear" onClick={onClear} title="Effacer l'historique">✕</button>
      </div>

      <div className="hist-list">
        {history.map(entry => {
          const delayed = entry.result.is_delayed;
          const prob    = Math.round(entry.result.delay_probability * 100);
          return (
            <button key={entry.id} className="hist-entry" onClick={() => onSelect(entry)}>
              <div className="hist-left">
                <div className="hist-route">
                  <strong>{entry.origin.iata}</strong>
                  <span className="hist-arrow">→</span>
                  <strong>{entry.destination.iata}</strong>
                  <span className="hist-airline">{entry.airline_code}</span>
                </div>
                <div className="hist-time">{formatDt(entry.departure_datetime)}</div>
              </div>
              <span className={`hist-badge ${delayed ? "hist-badge--delay" : "hist-badge--ok"}`}>
                {delayed ? `+${Math.round(entry.result.delay_minutes)}m` : "✓"} {prob}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
