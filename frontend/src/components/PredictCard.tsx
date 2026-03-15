"use client";

import { useState } from "react";
import type { Airport, AirlineComparison, Factor, PredictResponse, Timeline, WeatherData, WeatherForecast } from "@/lib/types";
import WeatherChart from "./WeatherChart";
import TimelineChart from "./TimelineChart";
import AirlineCompare from "./AirlineCompare";

interface Props {
  result:            PredictResponse;
  origin:            Airport | null;
  destination:       Airport | null;
  airlineCode:       string;
  destWeather:       WeatherData | null;
  forecast:          WeatherForecast | null;
  timeline:          Timeline | null;
  airlineComparison: AirlineComparison | null;
}

// ── Gauge demi-cercle ─────────────────────────────────
function ProbGauge({ prob, delayed }: { prob: number; delayed: boolean }) {
  const r    = 44;
  const cx   = 62, cy = 58;
  const circ = Math.PI * r;
  const dash = (prob / 100) * circ;
  const color      = delayed ? "var(--red)"   : "var(--green)";
  const trackColor = delayed ? "rgba(217,48,37,0.12)" : "rgba(30,142,62,0.12)";

  return (
    <svg viewBox="0 0 124 72" width="124" height="72">
      {/* Track */}
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={trackColor} strokeWidth="10" strokeLinecap="round"
      />
      {/* Fill */}
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={`${dash} ${circ}`}
        style={{ transition: "stroke-dasharray 1s cubic-bezier(0.34,1.56,0.64,1)" }}
      />
      {/* Value */}
      <text x={cx} y={cy - 6} textAnchor="middle"
        fontSize="24" fontWeight="800" fill={color}
        fontFamily="Roboto Mono, monospace">
        {prob}%
      </text>
      <text x={cx} y={cy + 11} textAnchor="middle"
        fontSize="7" fill="#9aa0a6" letterSpacing="1.2"
        fontFamily="Plus Jakarta Sans, sans-serif" fontWeight="600">
        PROBABILITÉ
      </text>
    </svg>
  );
}

// ── Section accordéon ─────────────────────────────────
function Section({
  title, icon, children, defaultOpen = true,
}: { title: string; icon: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="pc-section">
      <button className="pc-section-toggle" onClick={() => setOpen(o => !o)}>
        <span className="pc-section-icon">{icon}</span>
        <span className="pc-section-title">{title}</span>
        <span className={`pc-section-chevron${open ? " pc-section-chevron--open" : ""}`}>›</span>
      </button>
      {open && <div className="pc-section-body">{children}</div>}
    </div>
  );
}

// ── WeatherCol ────────────────────────────────────────
function weatherIcon(w: WeatherData): string {
  if (w.snowfall_cm > 0)               return "❄️";
  if (w.bad_weather && w.precip_mm > 5) return "⛈";
  if (w.precip_mm > 0.5)              return "🌧";
  if (w.wind_kmh > 40)                return "💨";
  if (w.visibility < 3000)            return "🌫";
  return "☀️";
}

function WeatherCol({
  label, airport, weather, usedForModel,
}: { label: string; airport: Airport | null; weather: WeatherData; usedForModel?: boolean }) {
  const bad = weather.bad_weather === 1;
  return (
    <div className={`wx-col${bad ? " wx-col--bad" : ""}`}>
      <div className="wx-col-header">
        <span className="wx-label">{label}</span>
        <span className="wx-iata">{airport?.iata}</span>
        {usedForModel && <span className="wx-model-badge">utilisée</span>}
      </div>
      <div className="wx-icon">{weatherIcon(weather)}</div>
      <div className="wx-city">{airport?.city ?? "—"}</div>
      <div className="wx-stats">
        <div className="wx-stat"><span className="wx-stat-icon">🌡</span><span className="wx-stat-val">{weather.temperature.toFixed(1)}°C</span></div>
        <div className="wx-stat"><span className="wx-stat-icon">💨</span><span className="wx-stat-val">{weather.wind_kmh.toFixed(0)} km/h</span></div>
        <div className="wx-stat"><span className="wx-stat-icon">🌧</span><span className="wx-stat-val">{weather.precip_mm.toFixed(1)} mm</span></div>
        <div className="wx-stat"><span className="wx-stat-icon">👁</span><span className="wx-stat-val">{(weather.visibility / 1000).toFixed(1)} km</span></div>
        {weather.snowfall_cm > 0 && (
          <div className="wx-stat"><span className="wx-stat-icon">❄️</span><span className="wx-stat-val">{weather.snowfall_cm.toFixed(1)} cm</span></div>
        )}
      </div>
      {bad && <div className="wx-bad-badge">⚠ Mauvais temps</div>}
    </div>
  );
}

// ── Carte principale ──────────────────────────────────
export default function PredictCard({
  result, origin, destination, airlineCode,
  destWeather, forecast, timeline, airlineComparison,
}: Props) {
  const delayed   = result.is_delayed;
  const prob      = Math.round(result.delay_probability * 100);
  const threshPct = Math.round(result.threshold_used * 100);
  const originWeather: WeatherData = { ...result.features_used.weather, snowfall_cm: 0 };

  return (
    <div className={`pc-card ${delayed ? "pc-card--delayed" : "pc-card--ontime"}`}>

      {/* ── Header coloré ── */}
      <div className="pc-header">
        <div className="pc-header-bg" />
        <div className="pc-header-content">
          <div className="pc-route">
            <span className="pc-iata">{origin?.iata ?? "—"}</span>
            <span className="pc-route-arrow">✈</span>
            <span className="pc-iata">{destination?.iata ?? "—"}</span>
          </div>
          <div className="pc-route-cities">{origin?.city} → {destination?.city}</div>
          <span className={`pc-status-badge ${delayed ? "pc-status-badge--delay" : "pc-status-badge--ok"}`}>
            {delayed ? "⚠ Retard probable" : "✓ Vol à l'heure"}
          </span>
        </div>
      </div>

      {/* ── Corps scrollable ── */}
      <div className="pc-body">

        {/* Gauge + métriques */}
        <div className="pc-hero">
          <ProbGauge prob={prob} delayed={delayed} />
          <div className="pc-hero-metrics">
            <div className="pc-metric">
              <span className="pc-metric-val" style={{ color: delayed ? "var(--red)" : "var(--text)" }}>
                {delayed ? `+${Math.round(result.delay_minutes)}` : "—"}
              </span>
              {delayed && <span className="pc-metric-unit">min</span>}
              <span className="pc-metric-label">{delayed ? "Retard estimé" : "À l'heure"}</span>
            </div>
            <div className="pc-metric">
              <span className="pc-metric-val">{result.features_used.dep_hour}</span>
              <span className="pc-metric-unit">h</span>
              <span className="pc-metric-label">Heure de départ</span>
            </div>
          </div>
        </div>

        {/* Barre de probabilité avec seuil */}
        <div className="pc-prob-wrap">
          <div className="pc-prob-track">
            <div className="pc-prob-fill" style={{ width: `${prob}%` }} />
            <div className="pc-prob-thresh" style={{ left: `${threshPct}%` }} />
          </div>
          <div className="pc-prob-labels">
            <span>0%</span>
            <span className="pc-prob-thresh-label">seuil {threshPct}%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Confiance + week-end */}
        <div className="pc-chips-row">
          <span className={`pc-conf-chip pc-conf-chip--${result.confidence}`}>
            {result.confidence === "high"   ? "🟢 Haute confiance"
           : result.confidence === "medium" ? "🟡 Confiance moy."
           :                                  "⚪ Faible confiance"}
          </span>
          {result.features_used.is_weekend === 1 && (
            <span className="pc-conf-chip">📅 Week-end</span>
          )}
        </div>

        {/* Facteurs */}
        {result.factors.length > 0 && (
          <Section
            title={delayed ? "Pourquoi ce délai ?" : "Facteurs analysés"}
            icon={delayed ? "⚠" : "⚙"}
            defaultOpen
          >
            <div className="factors-list">
              {result.factors.map((f: Factor, i: number) => (
                <span key={i} className={`factor-tag factor-tag--${f.severity}`}>{f.label}</span>
              ))}
            </div>
          </Section>
        )}

        {/* Météo */}
        <Section title="Météo aux aéroports" icon="🌤" defaultOpen>
          <div className="wx-panel">
            <WeatherCol label="Départ"  airport={origin}      weather={originWeather} usedForModel />
            <div className="wx-divider" />
            {destWeather
              ? <WeatherCol label="Arrivée" airport={destination} weather={destWeather} />
              : <div className="wx-col wx-col--loading"><div className="wx-label">Arrivée</div><div className="wx-icon">…</div></div>
            }
          </div>
          {forecast && forecast.hours.length >= 2 && (
            <div style={{ marginTop: 8 }}>
              <WeatherChart hours={forecast.hours} iata={forecast.iata} />
            </div>
          )}
        </Section>

        {/* Timeline */}
        {timeline && (
          <Section title="Meilleur horaire de départ" icon="⏱" defaultOpen>
            <TimelineChart
              points={timeline.points}
              threshold={timeline.threshold}
              bestHours={timeline.best_hours}
              worstHours={timeline.worst_hours}
              currentHour={result.features_used.dep_hour}
            />
          </Section>
        )}

        {/* Compagnies */}
        {airlineComparison && (
          <Section title="Compagnies alternatives" icon="✈" defaultOpen={false}>
            <AirlineCompare
              airlines={airlineComparison.airlines}
              selectedCode={airlineCode}
              threshold={result.threshold_used}
            />
          </Section>
        )}

      </div>
    </div>
  );
}
