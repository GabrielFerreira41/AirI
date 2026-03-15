import type { Airport, AirlineComparison, AirportSummary, LiveFlight, PredictRequest, PredictResponse, Timeline, WeatherData, WeatherForecast } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchAirports(): Promise<Airport[]> {
  const res = await fetch(`${API}/airports`);
  if (!res.ok) throw new Error("Impossible de charger les aéroports");
  const data = await res.json();
  return data.airports;
}

export async function predictDelay(req: PredictRequest): Promise<PredictResponse> {
  const res = await fetch(`${API}/predict`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Erreur ${res.status}`);
  }
  return res.json();
}

export async function fetchWeather(iata: string): Promise<WeatherData> {
  const res = await fetch(`${API}/weather/${iata}`);
  if (!res.ok) throw new Error("Météo non disponible");
  return res.json();
}

export async function fetchWeatherForecast(iata: string, dt: string): Promise<WeatherForecast> {
  const res = await fetch(`${API}/weather/${iata}/hourly?dt=${encodeURIComponent(dt)}`);
  if (!res.ok) throw new Error("Prévisions non disponibles");
  return res.json();
}

export async function fetchAirportsSummary(): Promise<AirportSummary[]> {
  const res = await fetch(`${API}/airports/summary`);
  if (!res.ok) throw new Error("Résumé aéroports non disponible");
  const data = await res.json();
  return data.airports;
}

export async function fetchLiveFlights(): Promise<LiveFlight[]> {
  const res = await fetch(`${API}/flights/live`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.flights ?? [];
}

export async function fetchTimeline(req: {
  origin: string; destination: string; airline_code: string; date: string;
}): Promise<Timeline> {
  const res = await fetch(`${API}/predict/timeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error("Timeline non disponible");
  return res.json();
}

export async function fetchAirlineComparison(req: {
  origin: string; destination: string; departure_datetime: string;
}): Promise<AirlineComparison> {
  const res = await fetch(`${API}/predict/airlines`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error("Comparaison non disponible");
  return res.json();
}

export async function fetchRouteStats(origin: string, dest: string) {
  const res = await fetch(`${API}/stats/${origin}/${dest}`);
  if (!res.ok) throw new Error("Stats non disponibles");
  return res.json();
}
