"use client";
import "leaflet/dist/leaflet.css";

import { useEffect, useRef, useState } from "react";
import type { Airport, PredictResponse } from "@/lib/types";

interface Props {
  airports:       Airport[];
  origin:         Airport | null;
  destination:    Airport | null;
  result:         PredictResponse | null;
  onAirportClick: (a: Airport) => void;
}

export default function MapView({ airports, origin, destination, result, onAirportClick }: Props) {
  const mapRef        = useRef<any>(null);
  const markersRef    = useRef<any[]>([]);
  const routeLayerRef = useRef<any>(null);
  const containerRef  = useRef<HTMLDivElement>(null);
  const initRef       = useRef(false);
  const [mapReady, setMapReady] = useState(false);

  // ── Init carte ──────────────────────────────────────────
  useEffect(() => {
    if (typeof window === "undefined" || !containerRef.current) return;
    if (initRef.current) return;

    let mounted = true;
    initRef.current = true;

    (async () => {
      const L = await import("leaflet");
      if (!mounted || !containerRef.current) return;

      // Reset _leaflet_id si le container a déjà été utilisé (hot reload)
      const el = containerRef.current as any;
      if (el?._leaflet_id) el._leaflet_id = undefined;

      const map = L.map(containerRef.current, {
        center: [55, -95],
        zoom: 4,
        zoomControl: true,
        minZoom: 3,
      });

      L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;
      setMapReady(true);

      setTimeout(() => {
        map.invalidateSize();
      }, 0);
    })();

    return () => {
      mounted = false;
      setMapReady(false);
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      if (routeLayerRef.current) {
        routeLayerRef.current.forEach((l: any) => l.remove());
        routeLayerRef.current = null;
      }
      mapRef.current?.remove();
      mapRef.current = null;
      initRef.current = false;
    };
  }, []);

  // ── Marqueurs — attend que la carte ET les aéroports soient prêts ──
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;

    let cancelled = false;

    (async () => {
      const L = await import("leaflet");
      if (cancelled || !mapRef.current) return;

      // Supprime anciens marqueurs
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];

      airports.forEach((airport) => {
        const isOrigin = origin?.iata === airport.iata;
        const isDest   = destination?.iata === airport.iata;
        const color    = isOrigin ? "#1a73e8" : isDest ? "#d93025" : "#5f6368";
        const size     = isOrigin || isDest ? 16 : 10;
        const ring     = isOrigin || isDest
          ? `<div style="position:absolute;inset:-5px;border-radius:50%;border:2px solid ${color};opacity:0.3;"></div>`
          : "";

        const icon = L.divIcon({
          className: "",
          html: `<div style="position:relative;width:${size}px;height:${size}px;">
            ${ring}
            <div style="
              width:${size}px;height:${size}px;
              background:${isOrigin || isDest ? color : "white"};
              border-radius:50%;
              border:${isOrigin || isDest ? "2px" : "1.5px"} solid ${color};
              box-shadow:${isOrigin || isDest
                ? "0 2px 8px rgba(0,0,0,0.25)"
                : "0 1px 3px rgba(0,0,0,0.2)"};
              cursor:pointer;
            "></div>
          </div>`,
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        });

        const marker = L.marker([airport.lat, airport.lon], { icon })
          .addTo(mapRef.current)
          .bindTooltip(
            `<strong>${airport.iata}</strong> · ${airport.city}<br/>
             <span style="color:#5f6368;font-size:11px">${airport.name}</span>`,
            { direction: "top", offset: [0, -8] }
          )
          .on("click", () => onAirportClick(airport));

        markersRef.current.push(marker);
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [mapReady, airports, origin, destination, onAirportClick]);

  // ── Route entre origine et destination ──────────────────
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;

    let cancelled = false;

    (async () => {
      const L = await import("leaflet");
      if (cancelled || !mapRef.current) return;

      // Nettoie l'ancienne route
      if (routeLayerRef.current) {
        routeLayerRef.current.forEach((l: any) => l.remove());
        routeLayerRef.current = null;
      }

      if (!origin || !destination) return;

      const color = result
        ? (result.is_delayed ? "#d93025" : "#1e8e3e")
        : "#1a73e8";

      // Courbe de Bézier quadratique
      const cp = {
        lat: (origin.lat + destination.lat) / 2
             + Math.abs(origin.lat - destination.lat) * 0.22,
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

      const shadow = L.polyline(pts, {
        color: "rgba(0,0,0,0.08)",
        weight: 6,
        opacity: 1,
      }).addTo(mapRef.current);

      const line = L.polyline(pts, {
        color,
        weight: 3,
        opacity: 0.9,
        dashArray: result ? undefined : "10 6",
      }).addTo(mapRef.current);

      routeLayerRef.current = [shadow, line];

      // Zoom sur la route
      mapRef.current.fitBounds(
        L.latLngBounds([
          [origin.lat, origin.lon],
          [destination.lat, destination.lon],
        ]),
        { padding: [100, 100], maxZoom: 7 }
      );

      setTimeout(() => {
        mapRef.current?.invalidateSize();
      }, 0);
    })();

    return () => {
      cancelled = true;
    };
  }, [mapReady, origin, destination, result]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
  );
}