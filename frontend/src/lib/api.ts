import type { Airport, PredictRequest, PredictResponse } from "./types";

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

export async function fetchWeather(iata: string) {
  const res = await fetch(`${API}/weather/${iata}`);
  if (!res.ok) throw new Error("Météo non disponible");
  return res.json();
}

export async function fetchRouteStats(origin: string, dest: string) {
  const res = await fetch(`${API}/stats/${origin}/${dest}`);
  if (!res.ok) throw new Error("Stats non disponibles");
  return res.json();
}
