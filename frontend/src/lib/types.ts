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
  }
  