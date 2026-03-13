"use client";

import { useState } from "react";
import type { Airport, PredictRequest } from "@/lib/types";

const AIRLINES = [
  { code: "AC", name: "Air Canada" },
  { code: "WS", name: "WestJet" },
  { code: "PD", name: "Porter Airlines" },
  { code: "F8", name: "Flair Airlines" },
  { code: "UA", name: "United Airlines" },
  { code: "DL", name: "Delta Air Lines" },
  { code: "AA", name: "American Airlines" },
  { code: "WN", name: "Southwest Airlines" },
];

interface Props {
  airports:       Airport[];
  origin:         Airport | null;
  destination:    Airport | null;
  onOriginChange: (a: Airport | null) => void;
  onDestChange:   (a: Airport | null) => void;
  onSubmit:       (req: PredictRequest) => void;
  loading:        boolean;
}

export default function FlightForm({
  airports, origin, destination,
  onOriginChange, onDestChange,
  onSubmit, loading,
}: Props) {
  const [airline,  setAirline]  = useState("AC");
  const [datetime, setDatetime] = useState(() => {
    const d = new Date();
    d.setHours(d.getHours() + 2, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });

  const canSubmit = !!origin && !!destination && !loading;

  return (
    <>
      <div className="card-header">
        <div className="card-icon">✈️</div>
        <span className="card-title">Paramètres du vol</span>
      </div>

      <div className="card-body">
        {/* Départ */}
        <div className="field">
          <label className="field-label">
            <span className="field-dot origin" /> Départ
          </label>
          <select
            className="field-select"
            value={origin?.iata || ""}
            onChange={e => onOriginChange(airports.find(a => a.iata === e.target.value) || null)}
          >
            <option value="">Sélectionner un aéroport</option>
            {airports.map(a => (
              <option key={a.iata} value={a.iata}>{a.iata} — {a.city}, {a.province}</option>
            ))}
          </select>
        </div>

        {/* Swap */}
        <div className="swap-row">
          <button
            className="swap-btn"
            onClick={() => { onOriginChange(destination); onDestChange(origin); }}
            title="Inverser"
          >⇅</button>
        </div>

        {/* Destination */}
        <div className="field">
          <label className="field-label">
            <span className="field-dot dest" /> Destination
          </label>
          <select
            className="field-select"
            value={destination?.iata || ""}
            onChange={e => onDestChange(airports.find(a => a.iata === e.target.value) || null)}
          >
            <option value="">Sélectionner un aéroport</option>
            {airports.filter(a => a.iata !== origin?.iata).map(a => (
              <option key={a.iata} value={a.iata}>{a.iata} — {a.city}, {a.province}</option>
            ))}
          </select>
        </div>

        {/* Compagnie */}
        <div className="field">
          <label className="field-label">Compagnie</label>
          <select className="field-select" value={airline} onChange={e => setAirline(e.target.value)}>
            {AIRLINES.map(a => (
              <option key={a.code} value={a.code}>{a.code} — {a.name}</option>
            ))}
          </select>
        </div>

        {/* Date */}
        <div className="field">
          <label className="field-label">Date & heure départ</label>
          <input
            type="datetime-local"
            className="field-input"
            value={datetime}
            onChange={e => setDatetime(e.target.value)}
          />
        </div>

        {/* Submit */}
        <button
          className="predict-btn"
          onClick={() => canSubmit && onSubmit({
            origin:             origin!.iata,
            destination:        destination!.iata,
            airline_code:       airline,
            departure_datetime: new Date(datetime).toISOString(),
          })}
          disabled={!canSubmit}
        >
          {loading
            ? <><span className="btn-spinner" /> Analyse…</>
            : "Prédire le retard"
          }
        </button>
      </div>
    </>
  );
}