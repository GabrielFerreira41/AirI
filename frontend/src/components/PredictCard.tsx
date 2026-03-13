"use client";

import type { Airport, PredictResponse } from "@/lib/types";

interface Props {
  result:      PredictResponse;
  origin:      Airport | null;
  destination: Airport | null;
}

export default function PredictCard({ result, origin, destination }: Props) {
  const delayed   = result.is_delayed;
  const prob      = Math.round(result.delay_probability * 100);
  const threshPct = Math.round(result.threshold_used * 100);
  const w         = result.features_used.weather;

  return (
    <div className={`result-card ${delayed ? "delayed" : "ontime"}`}>
      <div className="result-stripe" />

      <div className="result-body">

        {/* Top */}
        <div className="result-top">
          <div>
            <div className="result-title">
              {delayed ? "Retard probable" : "Vol à l'heure"}
            </div>
            <div className="result-subtitle">
              {origin?.iata} → {destination?.iata} · {origin?.city} → {destination?.city}
            </div>
          </div>
          <span className="result-badge">
            {delayed ? "⚠ Retardé" : "✓ À l'heure"}
          </span>
        </div>

        {/* Métriques */}
        <div className="metrics-row">
          <div className="metric-box">
            <div className="metric-value hi">{prob}%</div>
            <div className="metric-label">Probabilité</div>
          </div>
          <div className="metric-box">
            <div className="metric-value">
              {delayed ? `${Math.round(result.delay_minutes)} min` : "—"}
            </div>
            <div className="metric-label">{delayed ? "Retard" : "À l'heure"}</div>
          </div>
          <div className="metric-box">
            <div className="metric-value">{result.features_used.dep_hour}h</div>
            <div className="metric-label">Départ</div>
          </div>
        </div>

        {/* Barre */}
        <div className="prob-row">
          <span className="prob-pct">0%</span>
          <div className="prob-track">
            <div className="prob-fill" style={{ width: `${prob}%` }} />
            <div className="prob-threshold" style={{ left: `${threshPct}%` }} />
          </div>
          <span className="prob-pct">{prob}%</span>
        </div>

        {/* Météo */}
        <div className="weather-chips">
          <div className="w-chip">🌡 {w.temperature?.toFixed(1)}°C</div>
          <div className="w-chip">💨 {w.wind_kmh?.toFixed(0)} km/h</div>
          <div className="w-chip">🌧 {w.precip_mm?.toFixed(1)} mm</div>
          <div className="w-chip">👁 {(w.visibility / 1000)?.toFixed(1)} km</div>
          {w.bad_weather === 1 && <div className="w-chip warn">⚠ Mauvais temps</div>}
          {result.features_used.is_weekend === 1 && <div className="w-chip">📅 Week-end</div>}
        </div>

        {/* Confiance */}
        <div className="confidence-row">
          <span className="confidence-tag">
            {result.confidence === "high"   ? "🟢 Haute confiance"
           : result.confidence === "medium" ? "🟡 Confiance moyenne"
           :                                  "⚪ Faible confiance"}
          </span>
        </div>

      </div>
    </div>
  );
}