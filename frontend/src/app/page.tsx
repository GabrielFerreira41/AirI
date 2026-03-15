"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import FlightForm from "@/components/FlightForm";
import PredictCard from "@/components/PredictCard";
import HistoryPanel from "@/components/HistoryPanel";
import { fetchAirports, fetchAirportsSummary, fetchLiveFlights, predictDelay, fetchWeather, fetchWeatherForecast, fetchTimeline, fetchAirlineComparison } from "@/lib/api";
import type { Airport, AirlineComparison, AirportSummary, HistoryEntry, LiveFlight, PredictRequest, PredictResponse, Timeline, WeatherData, WeatherForecast } from "@/lib/types";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function Home() {
  const [airports, setAirports]               = useState<Airport[]>([]);
  const [airportsSummary, setAirportsSummary] = useState<AirportSummary[]>([]);
  const [liveFlights, setLiveFlights]         = useState<LiveFlight[]>([]);
  const [origin, setOrigin]                   = useState<Airport | null>(null);
  const [dest, setDest]                       = useState<Airport | null>(null);
  const [airlineCode, setAirlineCode]         = useState<string>("");
  const [result, setResult]                   = useState<PredictResponse | null>(null);
  const [destWeather, setDestWeather]         = useState<WeatherData | null>(null);
  const [forecast, setForecast]               = useState<WeatherForecast | null>(null);
  const [timeline, setTimeline]               = useState<Timeline | null>(null);
  const [airlineComparison, setAirlineComparison] = useState<AirlineComparison | null>(null);
  const [history, setHistory]                 = useState<HistoryEntry[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("airi-history") || "[]"); } catch { return []; }
  });
  const [loading, setLoading]                 = useState(false);
  const [error, setError]                     = useState<string | null>(null);
  const [time, setTime]                       = useState("");

  useEffect(() => {
    // Horloge
    const tick = () => setTime(new Date().toLocaleTimeString("fr-CA", { hour12: false }));
    tick();
    const clockId = setInterval(tick, 1000);

    // Aéroports + résumé météo initial
    fetchAirports().then(setAirports).catch(console.error);
    fetchAirportsSummary().then(setAirportsSummary).catch(console.error);

    // Vols en direct — fetch initial puis toutes les 60s
    const loadFlights = () => fetchLiveFlights().then(setLiveFlights).catch(console.error);
    loadFlights();
    const flightsId = setInterval(loadFlights, 60_000);

    // Rafraîchir le résumé météo toutes les 5min
    const summaryId = setInterval(
      () => fetchAirportsSummary().then(setAirportsSummary).catch(console.error),
      300_000
    );

    return () => {
      clearInterval(clockId);
      clearInterval(flightsId);
      clearInterval(summaryId);
    };
  }, []);

  const saveHistory = (entry: HistoryEntry) => {
    setHistory(prev => {
      const next = [entry, ...prev.filter(e => e.id !== entry.id)].slice(0, 5);
      localStorage.setItem("airi-history", JSON.stringify(next));
      return next;
    });
  };

  const handlePredict = async (req: PredictRequest) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setDestWeather(null);
    setForecast(null);
    setTimeline(null);
    setAirlineComparison(null);
    setAirlineCode(req.airline_code);
    try {
      const date = req.departure_datetime.split("T")[0];
      const [res, dw, fc, tl, ac] = await Promise.all([
        predictDelay(req),
        fetchWeather(req.destination),
        fetchWeatherForecast(req.origin, req.departure_datetime).catch(() => null),
        fetchTimeline({ origin: req.origin, destination: req.destination, airline_code: req.airline_code, date }).catch(() => null),
        fetchAirlineComparison({ origin: req.origin, destination: req.destination, departure_datetime: req.departure_datetime }).catch(() => null),
      ]);
      setResult(res);
      setDestWeather(dw);
      setForecast(fc);
      setTimeline(tl);
      setAirlineComparison(ac);
      if (origin && dest) {
        saveHistory({
          id: `${req.origin}-${req.destination}-${req.departure_datetime}`,
          origin, destination: dest,
          airline_code: req.airline_code,
          departure_datetime: req.departure_datetime,
          result: res,
          timestamp: Date.now(),
        });
      }
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
          airportsSummary={airportsSummary}
          liveFlights={liveFlights}
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
          <span className="app-title">AirL</span>
        </div>
        <div className="header-sep" />
        <div className="header-chip">
          <span className="chip-live" /> Modèle actif · LightGBM
        </div>
        <div className="header-sep" />
        {liveFlights.length > 0 && (
          <>
            <div className="header-chip">
              <span className="chip-live chip-live--blue" /> {liveFlights.length} vols en direct
            </div>
            <div className="header-sep" />
          </>
        )}
        <span className="time-display">{time}</span>
      </header>

      {/* ── Colonne gauche : formulaire + historique ── */}
      <div className="left-col">
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

        <HistoryPanel
          history={history}
          onSelect={(entry) => {
            setOrigin(entry.origin);
            setDest(entry.destination);
            setAirlineCode(entry.airline_code);
            setResult(entry.result);
            setDestWeather(null);
            setForecast(null);
            setTimeline(null);
            setAirlineComparison(null);
          }}
          onClear={() => {
            setHistory([]);
            localStorage.removeItem("airi-history");
          }}
        />
      </div>

      {/* ── Résultat flottant — droite ── */}
      {result && !loading && (
        <PredictCard
          result={result}
          origin={origin}
          destination={dest}
          airlineCode={airlineCode}
          destWeather={destWeather}
          forecast={forecast}
          timeline={timeline}
          airlineComparison={airlineComparison}
        />
      )}

      {/* ── Hint ── */}
      <div className="map-hint">
        Cliquez sur un aéroport pour le sélectionner
      </div>

    </main>
  );
}
