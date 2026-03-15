export interface WeatherData {
  temperature:  number;
  wind_kmh:     number;
  precip_mm:    number;
  visibility:   number;
  snowfall_cm:  number;
  bad_weather:  number;
}

export interface Airport {
    iata:     string;
    name:     string;
    city:     string;
    lat:      number;
    lon:      number;
    province: string;
  }
  
  export interface PredictRequest {
    origin:               string;
    destination:          string;
    airline_code:         string;
    departure_datetime:   string;
    distance_km?:         number;
  }
  
  export interface HourlyPoint {
    time:         string;
    hour:         number;
    label:        string;   // "17h"
    temperature:  number;
    wind_kmh:     number;
    precip_mm:    number;
    is_departure: boolean;
  }

  export interface WeatherForecast {
    iata:         string;
    departure_dt: string;
    hours:        HourlyPoint[];
  }

  export interface AirportSummary {
    iata:          string;
    city:          string;
    status:        "ok" | "watch" | "alert";
    delay_rate:    number;
    flights_today: number;
  }

  export interface LiveFlight {
    icao24:      string;
    callsign:    string;
    lat:         number;
    lon:         number;
    altitude_m:  number;
    velocity_ms: number;
    heading:     number;
  }

  // ── Timeline ──────────────────────────────────────────────────────
  export interface TimelinePoint {
    hour:          number;
    probability:   number;
    is_delayed:    boolean;
    delay_minutes: number;
  }
  export interface Timeline {
    points:      TimelinePoint[];
    best_hours:  number[];
    worst_hours: number[];
    threshold:   number;
  }

  // ── Comparaison compagnies ────────────────────────────────────────
  export interface AirlineResult {
    code:          string;
    name:          string;
    probability:   number;
    is_delayed:    boolean;
    delay_minutes: number;
  }
  export interface AirlineComparison {
    airlines: AirlineResult[];
  }

  // ── Historique de session ─────────────────────────────────────────
  export interface HistoryEntry {
    id:                 string;
    origin:             Airport;
    destination:        Airport;
    airline_code:       string;
    departure_datetime: string;
    result:             PredictResponse;
    timestamp:          number;
  }

  export interface Factor {
    label:    string;
    severity: "alert" | "warn" | "info";
  }

  export interface PredictResponse {
    is_delayed:        boolean;
    delay_probability: number;
    delay_minutes:     number;
    confidence:        "high" | "medium" | "low";
    threshold_used:    number;
    features_used:     {
      weather: {
        temperature: number;
        wind_kmh:    number;
        precip_mm:   number;
        visibility:  number;
        bad_weather: number;
      };
      dep_hour:   number;
      is_weekend: number;
    };
    factors: Factor[];
  }
  