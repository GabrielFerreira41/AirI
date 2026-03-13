"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import FlightForm from "@/components/FlightForm";
import PredictCard from "@/components/PredictCard";
import { fetchAirports, predictDelay } from "@/lib/api";
import type { Airport, PredictRequest, PredictResponse } from "@/lib/types";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function Home() {
  const [airports, setAirports] = useState<Airport[]>([]);
  const [origin, setOrigin]     = useState<Airport | null>(null);
  const [dest, setDest]         = useState<Airport | null>(null);
  const [result, setResult]     = useState<PredictResponse | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [time, setTime]         = useState("");

  useEffect(() => {
    fetchAirports().then(setAirports).catch(console.error);
    const tick = () => setTime(new Date().toLocaleTimeString("fr-CA", { hour12: false }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const handlePredict = async (req: PredictRequest) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await predictDelay(req);
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Erreur lors de la prédiction");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="app-shell">

      {/* ── Carte plein écran ── */}
      <div className="map-fullscreen">
        <MapView
          airports={airports}
          origin={origin}
          destination={dest}
          result={result}
          onAirportClick={(airport) => {
            if (!origin) { setOrigin(airport); return; }
            if (!dest && airport.iata !== origin.iata) { setDest(airport); return; }
            setOrigin(airport); setDest(null); setResult(null);
          }}
        />
      </div>

      {/* ── Header flottant centré ── */}
      <header className="app-header">
        <div className="logo-group">
          <div className="logo-icon-wrap">✈</div>
          <span className="app-title">Flight<span>Sense</span></span>
        </div>
        <div className="header-sep" />
        <div className="header-chip">
          <span className="chip-live" /> Modèle actif · LightGBM
        </div>
        <div className="header-sep" />
        <span className="time-display">{time}</span>
      </header>

      {/* ── Formulaire flottant — gauche ── */}
      <div className="form-card">
        <FlightForm
          airports={airports}
          origin={origin}
          destination={dest}
          onOriginChange={setOrigin}
          onDestChange={(a) => { setDest(a); setResult(null); }}
          onSubmit={handlePredict}
          loading={loading}
        />
        {loading && (
          <div className="form-loading">
            <div className="form-spinner" />
            Analyse en cours…
          </div>
        )}
        {error && (
          <div className="form-error">
            <span>⚠️</span> {error}
          </div>
        )}
      </div>

      {/* ── Résultat flottant — droite ── */}
      {result && !loading && (
        <PredictCard result={result} origin={origin} destination={dest} />
      )}

      {/* ── Hint ── */}
      <div className="map-hint">
        Cliquez sur un aéroport pour le sélectionner
      </div>

    </main>
  );
}