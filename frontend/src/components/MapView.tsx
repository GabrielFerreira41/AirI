"use client";
import "leaflet/dist/leaflet.css";

import { useEffect, useRef, useState } from "react";
import type { Airport, AirportSummary, LiveFlight, PredictResponse, WeatherData } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Props {
  airports:        Airport[];
  airportsSummary: AirportSummary[];
  liveFlights:     LiveFlight[];
  origin:          Airport | null;
  destination:     Airport | null;
  result:          PredictResponse | null;
  onAirportClick:  (a: Airport) => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_COLOR = { ok: "#1e8e3e", watch: "#f9ab00", alert: "#d93025" } as const;
const STATUS_LABEL = { ok: "Normal", watch: "Vigilance", alert: "Perturbé" } as const;

function buildTooltip(
  airport:  Airport,
  summary:  AirportSummary | undefined,
  weather:  WeatherData | null,
): string {
  const status      = summary?.status ?? "ok";
  const statusColor = STATUS_COLOR[status];
  const statusLabel = STATUS_LABEL[status];
  const delay_rate    = summary?.delay_rate    ?? 0.19;
  const flights_today = summary?.flights_today ?? 0;

  const weatherRow = weather
    ? `<div class="rt-weather">
        <span class="rt-chip">🌡 ${weather.temperature.toFixed(1)}°C</span>
        <span class="rt-chip">💨 ${weather.wind_kmh.toFixed(0)} km/h</span>
        <span class="rt-chip">🌧 ${weather.precip_mm.toFixed(1)} mm</span>
        ${weather.snowfall_cm > 0 ? `<span class="rt-chip">❄ ${weather.snowfall_cm.toFixed(1)} cm</span>` : ""}
      </div>`
    : `<div class="rt-loading">Chargement météo…</div>`;

  return `<div class="rt-wrap">
    <div class="rt-header">
      <div class="rt-name"><strong>${airport.iata}</strong> · ${airport.city}</div>
      <span class="rt-status" style="background:${statusColor}20;color:${statusColor};border-color:${statusColor}40">
        ${statusLabel}
      </span>
    </div>
    ${weatherRow}
    <div class="rt-stats">
      <span class="rt-stat">📊 Retards&nbsp;<strong>${(delay_rate * 100).toFixed(0)}%</strong></span>
      <span class="rt-stat">✈ <strong>${flights_today}</strong> vols/jour</span>
    </div>
  </div>`;
}

function buildMarkerHtml(
  isOrigin: boolean,
  isDest: boolean,
  color: string,
  size: number,
  status: AirportSummary["status"] | undefined,
): string {
  const ring = isOrigin || isDest
    ? `<div style="position:absolute;inset:-5px;border-radius:50%;border:2px solid ${color};opacity:0.3;"></div>`
    : "";

  const badge = status
    ? `<div style="
        position:absolute;bottom:-2px;right:-2px;
        width:7px;height:7px;border-radius:50%;
        background:${STATUS_COLOR[status]};
        border:1.5px solid white;
        box-shadow:0 1px 2px rgba(0,0,0,0.3);
      "></div>`
    : "";

  return `<div style="position:relative;width:${size}px;height:${size}px;">
    ${ring}
    <div style="
      width:${size}px;height:${size}px;
      background:${isOrigin || isDest ? color : "white"};
      border-radius:50%;
      border:${isOrigin || isDest ? "2px" : "1.5px"} solid ${color};
      box-shadow:${isOrigin || isDest ? "0 2px 8px rgba(0,0,0,0.25)" : "0 1px 3px rgba(0,0,0,0.2)"};
      cursor:pointer;
    "></div>
    ${badge}
  </div>`;
}

function buildPlaneHtml(heading: number, altitude_m: number): string {
  // Couleur selon altitude : bas=orange, haut=bleu
  const color = altitude_m < 5000 ? "#f9ab00" : altitude_m < 10000 ? "#1a73e8" : "#5f6368";
  return `<div style="
    transform:rotate(${heading}deg);
    font-size:13px;line-height:1;
    color:${color};
    filter:drop-shadow(0 1px 2px rgba(0,0,0,0.4));
    transition:transform 1s ease;
  ">✈</div>`;
}

// ── Composant ────────────────────────────────────────────────────────────────

export default function MapView({
  airports, airportsSummary, liveFlights,
  origin, destination, result, onAirportClick,
}: Props) {
  const mapRef          = useRef<any>(null);
  const markersRef      = useRef<any[]>([]);
  const routeLayerRef   = useRef<any>(null);
  const planeMarkersRef = useRef<any[]>([]);
  const containerRef    = useRef<HTMLDivElement>(null);
  const initRef         = useRef(false);
  const [mapReady, setMapReady] = useState(false);

  // Index summary par IATA — mis à jour immédiatement à chaque rendu
  const summaryMap    = useRef<Map<string, AirportSummary>>(new Map());
  summaryMap.current  = new Map(airportsSummary.map(s => [s.iata, s]));

  // Cache météo par aéroport — chargée lazily au premier survol
  const weatherCache = useRef<Map<string, WeatherData>>(new Map());

  // ── 1. Init carte ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (typeof window === "undefined" || !containerRef.current) return;
    if (initRef.current) return;
    initRef.current = true;

    let mounted = true;
    (async () => {
      const L = await import("leaflet");
      if (!mounted || !containerRef.current) return;

      const el = containerRef.current as any;
      if (el?._leaflet_id) el._leaflet_id = undefined;

      const map = L.map(containerRef.current, { center: [55, -95], zoom: 4, zoomControl: true, minZoom: 3 });
      L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;
      setMapReady(true);
      setTimeout(() => map.invalidateSize(), 0);
    })();

    return () => {
      mounted = false;
      setMapReady(false);
      markersRef.current.forEach(m => m.remove());
      markersRef.current = [];
      planeMarkersRef.current.forEach(m => m.remove());
      planeMarkersRef.current = [];
      if (routeLayerRef.current) {
        routeLayerRef.current.forEach((l: any) => l.remove());
        routeLayerRef.current = null;
      }
      mapRef.current?.remove();
      mapRef.current = null;
      initRef.current = false;
    };
  }, []);

  // ── 2. Marqueurs aéroports ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    let cancelled = false;

    (async () => {
      const L = await import("leaflet");
      if (cancelled || !mapRef.current) return;

      markersRef.current.forEach(m => m.remove());
      markersRef.current = [];

      airports.forEach(airport => {
        const isOrigin = origin?.iata === airport.iata;
        const isDest   = destination?.iata === airport.iata;
        const color    = isOrigin ? "#1a73e8" : isDest ? "#d93025" : "#5f6368";
        const size     = isOrigin || isDest ? 16 : 10;
        const summary  = summaryMap.current.get(airport.iata);

        const icon = L.divIcon({
          className: "",
          html: buildMarkerHtml(isOrigin, isDest, color, size, summary?.status),
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        });

        const marker = L.marker([airport.lat, airport.lon], { icon })
          .addTo(mapRef.current)
          .bindTooltip("", {
            direction: "top",
            offset: [0, -10],
            className: "rt-tooltip",
          });

        // Contenu construit au survol — météo chargée lazily et mise en cache
        marker.on("tooltipopen", () => {
          const summary = summaryMap.current.get(airport.iata);
          const cached  = weatherCache.current.get(airport.iata);

          // Affiche immédiatement avec les données disponibles
          marker.setTooltipContent(buildTooltip(airport, summary, cached ?? null));

          // Si météo pas encore en cache, la fetcher
          if (!cached) {
            fetch(`${API}/weather/${airport.iata}`)
              .then(r => r.json())
              .then((wx: WeatherData) => {
                weatherCache.current.set(airport.iata, wx);
                marker.setTooltipContent(buildTooltip(airport, summary, wx));
              })
              .catch(() => {});
          }
        });

        marker.on("click", () => onAirportClick(airport));
        markersRef.current.push(marker);
      });
    })();

    return () => { cancelled = true; };
  }, [mapReady, airports, origin, destination, onAirportClick, airportsSummary]);

  // ── 3. Route ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    let cancelled = false;

    (async () => {
      const L = await import("leaflet");
      if (cancelled || !mapRef.current) return;

      if (routeLayerRef.current) {
        routeLayerRef.current.forEach((l: any) => l.remove());
        routeLayerRef.current = null;
      }
      if (!origin || !destination) return;

      const color = result ? (result.is_delayed ? "#d93025" : "#1e8e3e") : "#1a73e8";
      const cp = {
        lat: (origin.lat + destination.lat) / 2 + Math.abs(origin.lat - destination.lat) * 0.22,
        lon: (origin.lon + destination.lon) / 2,
      };

      const pts: [number, number][] = [];
      for (let i = 0; i <= 50; i++) {
        const t = i / 50;
        pts.push([
          (1-t)*(1-t)*origin.lat + 2*(1-t)*t*cp.lat + t*t*destination.lat,
          (1-t)*(1-t)*origin.lon + 2*(1-t)*t*cp.lon + t*t*destination.lon,
        ]);
      }

      const shadow = L.polyline(pts, { color: "rgba(0,0,0,0.08)", weight: 6, opacity: 1 }).addTo(mapRef.current);
      const line   = L.polyline(pts, { color, weight: 3, opacity: 0.9, dashArray: result ? undefined : "10 6" }).addTo(mapRef.current);
      routeLayerRef.current = [shadow, line];

      mapRef.current.fitBounds(
        L.latLngBounds([[origin.lat, origin.lon], [destination.lat, destination.lon]]),
        { padding: [100, 100], maxZoom: 7 }
      );
      setTimeout(() => mapRef.current?.invalidateSize(), 0);
    })();

    return () => { cancelled = true; };
  }, [mapReady, origin, destination, result]);

  // ── 4. Avions en direct ───────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    let cancelled = false;

    (async () => {
      const L = await import("leaflet");
      if (cancelled || !mapRef.current) return;

      planeMarkersRef.current.forEach(m => m.remove());
      planeMarkersRef.current = [];

      liveFlights.forEach(flight => {
        const icon = L.divIcon({
          className: "",
          html: buildPlaneHtml(flight.heading, flight.altitude_m),
          iconSize: [16, 16],
          iconAnchor: [8, 8],
        });

        const alt  = flight.altitude_m.toLocaleString("fr-CA");
        const spd  = Math.round(flight.velocity_ms * 3.6);
        const tip  = `<div class="rt-wrap rt-wrap--plane">
          <div class="rt-name"><strong>${flight.callsign}</strong></div>
          <div class="rt-weather">
            <span class="rt-chip">↑ ${alt} m</span>
            <span class="rt-chip">⚡ ${spd} km/h</span>
          </div>
        </div>`;

        const m = L.marker([flight.lat, flight.lon], { icon, zIndexOffset: -100 })
          .addTo(mapRef.current)
          .bindTooltip(tip, { direction: "top", offset: [0, -8], className: "rt-tooltip" });

        planeMarkersRef.current.push(m);
      });
    })();

    return () => { cancelled = true; };
  }, [mapReady, liveFlights]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}
