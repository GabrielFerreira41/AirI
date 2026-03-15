"""
backend/main.py — FastAPI Flight Delay Predictor
=================================================
Endpoints :
  GET  /                    → health check
  GET  /airports            → liste aéroports canadiens
  GET  /flights/{iata}      → vols au départ (OpenSky)
  POST /predict             → prédiction retard
  GET  /weather/{iata}      → météo actuelle
  GET  /stats/{origin}/{dest} → historique retards route

Setup :
  cd backend
  uv init && uv venv
  source .venv/bin/activate
  uv add fastapi uvicorn joblib lightgbm scikit-learn pandas numpy requests python-dotenv
  uv run uvicorn main:app --reload --port 8000
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()
log = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Flight Delay Predictor API",
    description="Prédiction de retards de vols au départ du Canada",
    version="1.0.0",
)

# CORS — autorise le frontend Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ← remplace la liste par "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# Chargement des modèles au démarrage                                 #
# ------------------------------------------------------------------ #
MODELS_DIR = Path(__file__).parent / "models"

models = {}

@app.on_event("startup")
async def load_models():
    global models
    try:
        models["clf"]      = joblib.load(MODELS_DIR / "classifier_lgbm.joblib")
        models["reg"]      = joblib.load(MODELS_DIR / "regressor_lgbm.joblib")
        models["encoders"] = joblib.load(MODELS_DIR / "encoders.joblib")

        with open(MODELS_DIR / "inference_meta.json") as f:
            models["meta"] = json.load(f)

        log.info("Modeles charges avec succes")
        log.info(f"  Threshold : {models['meta']['lgbm_threshold']:.2f}")
        log.info(f"  Features  : {len(models['meta']['feature_names'])} colonnes")
    except FileNotFoundError as e:
        log.warning(f"Modeles non trouves : {e}")
        log.warning("Lance d'abord : uv run python train.py dans ml/")


# ------------------------------------------------------------------ #
# Données statiques aéroports                                         #
# ------------------------------------------------------------------ #
AIRPORTS = [
    {"iata": "YYZ", "name": "Toronto Pearson",      "city": "Toronto",    "lat": 43.6777, "lon": -79.6248, "province": "ON"},
    {"iata": "YVR", "name": "Vancouver Intl",        "city": "Vancouver",  "lat": 49.1939, "lon": -123.1840,"province": "BC"},
    {"iata": "YUL", "name": "Montréal Trudeau",      "city": "Montréal",   "lat": 45.4706, "lon": -73.7408, "province": "QC"},
    {"iata": "YYC", "name": "Calgary Intl",          "city": "Calgary",    "lat": 51.1215, "lon": -114.0127,"province": "AB"},
    {"iata": "YEG", "name": "Edmonton Intl",         "city": "Edmonton",   "lat": 53.3097, "lon": -113.5800,"province": "AB"},
    {"iata": "YOW", "name": "Ottawa Macdonald-Cartier","city": "Ottawa",   "lat": 45.3225, "lon": -75.6692, "province": "ON"},
    {"iata": "YHZ", "name": "Halifax Stanfield",     "city": "Halifax",    "lat": 44.8808, "lon": -63.5086, "province": "NS"},
    {"iata": "YWG", "name": "Winnipeg Richardson",   "city": "Winnipeg",   "lat": 49.9100, "lon": -97.2398, "province": "MB"},
    {"iata": "YQB", "name": "Québec City Jean-Lesage","city": "Québec",    "lat": 46.7911, "lon": -71.3933, "province": "QC"},
    {"iata": "YYJ", "name": "Victoria Intl",         "city": "Victoria",   "lat": 48.6469, "lon": -123.4258,"province": "BC"},
    {"iata": "YQR", "name": "Regina Intl",           "city": "Regina",     "lat": 50.4319, "lon": -104.6658,"province": "SK"},
    {"iata": "YXE", "name": "Saskatoon Diefenbaker", "city": "Saskatoon",  "lat": 52.1708, "lon": -106.6997,"province": "SK"},
]

AIRPORTS_BY_IATA = {a["iata"]: a for a in AIRPORTS}


# ------------------------------------------------------------------ #
# Schémas Pydantic                                                    #
# ------------------------------------------------------------------ #
class PredictRequest(BaseModel):
    origin: str                  # IATA ex: "YUL"
    destination: str             # IATA ex: "JFK"
    airline_code: str            # ex: "AC"
    departure_datetime: str      # ISO format "2024-06-15T14:30:00"
    distance_km: float = None    # optionnel, calculé si absent

class Factor(BaseModel):
    label:    str
    severity: str   # "alert" | "warn" | "info"

class PredictResponse(BaseModel):
    is_delayed: bool
    delay_probability: float
    delay_minutes: float
    confidence: str
    threshold_used: float
    features_used: dict
    factors: list[Factor]

class TimelineRequest(BaseModel):
    origin:      str
    destination: str
    airline_code: str
    date:        str   # "2026-03-15"

class TimelinePoint(BaseModel):
    hour:          int
    probability:   float
    is_delayed:    bool
    delay_minutes: float

class AirlinesRequest(BaseModel):
    origin:             str
    destination:        str
    departure_datetime: str

class AirlineResult(BaseModel):
    code:          str
    name:          str
    probability:   float
    is_delayed:    bool
    delay_minutes: float

AIRLINE_NAMES = {
    "AC": "Air Canada",
    "WS": "WestJet",
    "PD": "Porter",
    "F8": "Flair",
    "UA": "United",
    "DL": "Delta",
    "AA": "American",
    "WN": "Southwest",
}



# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #
def get_weather_now(iata: str, lat: float, lon: float, timeout: int = 10) -> dict:
    """Récupère la météo actuelle via Open-Meteo forecast API."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":       lat,
            "longitude":      lon,
            "current":        [
                "temperature_2m", "precipitation", "windspeed_10m",
                "visibility", "snowfall", "weathercode",
            ],
            "timezone":       "auto",
            "windspeed_unit": "kmh",
        }
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()["current"]

        wind    = data.get("windspeed_10m", 0) or 0
        precip  = data.get("precipitation", 0) or 0
        vis     = data.get("visibility", 10000) or 10000
        snow    = data.get("snowfall", 0) or 0

        return {
            "temperature": data.get("temperature_2m", 15),
            "wind_kmh":    wind,
            "precip_mm":   precip,
            "visibility":  vis,
            "snowfall_cm": snow,
            "bad_weather": int(wind > 40 or precip > 5 or vis < 1000 or snow > 2),
        }
    except Exception as e:
        log.warning(f"Météo non disponible pour {iata}: {e}")
        return {
            "temperature": 15.0, "wind_kmh": 10.0, "precip_mm": 0.0,
            "visibility": 10000.0, "snowfall_cm": 0.0, "bad_weather": 0,
        }


def build_feature_vector(req: PredictRequest, weather: dict) -> pd.DataFrame:
    """Construit le vecteur de features pour l'inférence."""
    dt = datetime.fromisoformat(req.departure_datetime)

    # Encodage catégoriel
    encoders = models.get("encoders", {})

    def encode(col, val):
        le = encoders.get(col)
        if le is None:
            return 0
        try:
            return int(le.transform([val])[0])
        except ValueError:
            # Valeur inconnue → classe la plus fréquente (index 0)
            return 0

    hour = dt.hour
    dow  = dt.weekday()
    month = dt.month

    # Stats historiques par défaut (médianes dataset)
    # En production, ces valeurs viendraient d'une DB avec les stats en temps réel
    features = {
        # Temporelles
        "dep_hour":           hour,
        "dep_hour_sin":       np.sin(2 * np.pi * hour / 24),
        "dep_hour_cos":       np.cos(2 * np.pi * hour / 24),
        "day_of_week":        dow,
        "dow_sin":            np.sin(2 * np.pi * dow / 7),
        "dow_cos":            np.cos(2 * np.pi * dow / 7),
        "month":              month,
        "month_sin":          np.sin(2 * np.pi * month / 12),
        "month_cos":          np.cos(2 * np.pi * month / 12),
        "year":               dt.year,
        "is_weekend":         int(dow >= 5),
        "is_holiday_season":  int(
            (month == 12 and dt.day >= 20) or
            (month == 1  and dt.day <= 5)  or
            (month == 7)
        ),
        # Compagnie — stats moyennes si inconnue
        "airline_avg_delay":   8.5,
        "airline_delay_rate":  0.18,
        "airline_market_share":0.08,
        # Route — stats moyennes si inconnue
        "route_avg_delay":     9.2,
        "route_delay_rate":    0.19,
        "origin_avg_delay":    8.1,
        "origin_delay_rate":   0.17,
        "dest_avg_arr_delay":  7.8,
        "DISTANCE":            req.distance_km or 1200.0,
        # Propagation — pas d'info en temps réel → 0
        "prev_dep_delay":      0.0,
        "prev_3_avg_delay":    0.0,
        "prev_was_delayed":    0.0,
        # Météo
        "temperature":         weather["temperature"],
        "wind_kmh":            weather["wind_kmh"],
        "precip_mm":           weather["precip_mm"],
        "visibility":          weather["visibility"],
        "bad_weather":         weather["bad_weather"],
        "snowfall_cm":         weather["snowfall_cm"],
        # Catégorielles encodées
        "AIRLINE_CODE_enc":    encode("AIRLINE_CODE", req.airline_code),
        "ORIGIN_enc":          encode("ORIGIN", req.origin),
        "DEST_enc":            encode("DEST", req.destination),
    }

    # Ordonne selon feature_names du modèle
    feature_names = models["meta"]["feature_names"]
    row = {k: features.get(k, 0) for k in feature_names}
    return pd.DataFrame([row])


_SEVERITY_ORDER = {"alert": 0, "warn": 1, "info": 2}

def build_factors(req: "PredictRequest", weather: dict, dt: "datetime") -> list[dict]:
    """Génère les facteurs explicatifs triés par sévérité (max 5)."""
    factors: list[dict] = []
    iata  = req.origin.upper()
    wind  = weather["wind_kmh"]
    precip= weather["precip_mm"]
    vis   = weather["visibility"]
    snow  = weather["snowfall_cm"]
    temp  = weather["temperature"]
    hour  = dt.hour
    dow   = dt.weekday()
    month = dt.month

    # ── Météo ──────────────────────────────────────────────────────
    if wind > 60:
        factors.append({"label": f"Vent violent à {iata} ({wind:.0f} km/h)", "severity": "alert"})
    elif wind > 40:
        factors.append({"label": f"Vent fort à {iata} ({wind:.0f} km/h)", "severity": "alert"})
    elif wind > 25:
        factors.append({"label": f"Vent modéré à {iata} ({wind:.0f} km/h)", "severity": "warn"})

    if precip > 10:
        factors.append({"label": f"Très fortes précipitations ({precip:.1f} mm)", "severity": "alert"})
    elif precip > 5:
        factors.append({"label": f"Fortes précipitations ({precip:.1f} mm)", "severity": "alert"})
    elif precip > 1:
        factors.append({"label": f"Précipitations légères ({precip:.1f} mm)", "severity": "warn"})

    if snow > 5:
        factors.append({"label": f"Importantes chutes de neige ({snow:.1f} cm)", "severity": "alert"})
    elif snow > 2:
        factors.append({"label": f"Chutes de neige ({snow:.1f} cm)", "severity": "alert"})
    elif snow > 0:
        factors.append({"label": f"Légères chutes de neige ({snow:.1f} cm)", "severity": "warn"})

    if vis < 500:
        factors.append({"label": f"Visibilité très faible ({vis/1000:.1f} km)", "severity": "alert"})
    elif vis < 1000:
        factors.append({"label": f"Faible visibilité ({vis/1000:.1f} km)", "severity": "alert"})
    elif vis < 3000:
        factors.append({"label": f"Visibilité réduite ({vis/1000:.1f} km)", "severity": "warn"})

    if temp < -25:
        factors.append({"label": f"Grand froid ({temp:.0f}°C)", "severity": "warn"})
    elif temp < -15:
        factors.append({"label": f"Froid intense ({temp:.0f}°C)", "severity": "info"})

    # ── Heure de départ ────────────────────────────────────────────
    if 7 <= hour <= 9:
        factors.append({"label": f"Heure de pointe matinale ({hour}h)", "severity": "warn"})
    elif 16 <= hour <= 20:
        factors.append({"label": f"Heure de pointe vespérale ({hour}h)", "severity": "warn"})

    # ── Période ───────────────────────────────────────────────────
    if dow >= 5:
        factors.append({"label": "Week-end (trafic élevé)", "severity": "info"})
    if (month == 12 and dt.day >= 20) or (month == 1 and dt.day <= 5):
        factors.append({"label": "Période des fêtes", "severity": "warn"})
    elif month == 7:
        factors.append({"label": "Haute saison estivale", "severity": "warn"})

    # ── Route historique (valeurs médianes du modèle) ─────────────
    route_delay_rate = 0.19   # médiane du dataset BTS
    if route_delay_rate > 0.30:
        factors.append({"label": f"Route très retardée ({route_delay_rate*100:.0f}%)", "severity": "alert"})
    elif route_delay_rate > 0.25:
        factors.append({"label": f"Route souvent retardée ({route_delay_rate*100:.0f}%)", "severity": "warn"})
    else:
        factors.append({"label": f"Route historiquement retardée ({route_delay_rate*100:.0f}%)", "severity": "info"})

    # ── Distance ─────────────────────────────────────────────────
    distance = req.distance_km or 1200.0
    if distance > 3000:
        factors.append({"label": f"Long trajet ({distance:.0f} km) — risque de propagation", "severity": "warn"})

    # Trier par sévérité, garder les 5 plus importants
    factors.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 9))
    return factors[:5]


# ------------------------------------------------------------------ #
# Endpoints                                                           #
# ------------------------------------------------------------------ #
@app.get("/")
def health():
    return {
        "status":    "ok",
        "models_loaded": "clf" in models,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/airports")
def get_airports():
    """Retourne la liste des aéroports canadiens avec coordonnées."""
    return {"airports": AIRPORTS}


@app.get("/airports/{iata}")
def get_airport(iata: str):
    airport = AIRPORTS_BY_IATA.get(iata.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Aéroport {iata} non trouvé")
    return airport


@app.get("/weather/{iata}")
def get_weather(iata: str):
    """Météo actuelle à l'aéroport."""
    airport = AIRPORTS_BY_IATA.get(iata.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Aéroport {iata} non trouvé")

    weather = get_weather_now(iata, airport["lat"], airport["lon"])
    return {
        "iata":      iata,
        "city":      airport["city"],
        "timestamp": datetime.now().isoformat(),
        **weather,
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    """Prédit si un vol sera retardé et de combien de minutes."""
    if "clf" not in models:
        raise HTTPException(status_code=503, detail="Modèles non chargés")

    # Météo à l'origine
    origin_airport = AIRPORTS_BY_IATA.get(req.origin.upper())
    weather = get_weather_now(
        req.origin,
        origin_airport["lat"] if origin_airport else 45.0,
        origin_airport["lon"] if origin_airport else -75.0,
    )

    dt = datetime.fromisoformat(req.departure_datetime)

    # Vecteur de features
    X = build_feature_vector(req, weather)

    # Classification
    threshold    = models["meta"]["lgbm_threshold"]
    delay_prob   = float(models["clf"].predict_proba(X)[0][1])
    is_delayed   = delay_prob >= threshold

    # Régression (seulement si probable retard)
    if is_delayed:
        log_pred     = models["reg"].predict(X)[0]
        delay_min    = float(np.expm1(log_pred))
        delay_min    = max(0.0, round(delay_min, 1))
    else:
        delay_min = 0.0

    # Niveau de confiance
    if delay_prob > 0.75 or delay_prob < 0.25:
        confidence = "high"
    elif delay_prob > 0.60 or delay_prob < 0.40:
        confidence = "medium"
    else:
        confidence = "low"

    return PredictResponse(
        is_delayed        = is_delayed,
        delay_probability = round(delay_prob, 4),
        delay_minutes     = delay_min,
        confidence        = confidence,
        threshold_used    = threshold,
        features_used     = {
            "weather":     weather,
            "dep_hour":    dt.hour,
            "is_weekend":  int(dt.weekday() >= 5),
        },
        factors = build_factors(req, weather, dt),
    )


@app.get("/weather/{iata}/hourly")
def get_weather_hourly(iata: str, dt: str):
    """Prévisions météo horaires autour de l'heure de départ (±6h)."""
    airport = AIRPORTS_BY_IATA.get(iata.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Aéroport {iata} non trouvé")

    try:
        departure = datetime.fromisoformat(dt)
    except ValueError:
        raise HTTPException(status_code=400, detail="Format datetime invalide (ISO 8601)")

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":       airport["lat"],
            "longitude":      airport["lon"],
            "hourly":         ["temperature_2m", "precipitation", "windspeed_10m", "weathercode"],
            "timezone":       "auto",
            "windspeed_unit": "kmh",
            "forecast_days":  10,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()["hourly"]
        times = data["time"]  # ["2026-03-15T17:00", ...]

        # Trouver l'index le plus proche de l'heure de départ
        dep_str = departure.strftime("%Y-%m-%dT%H:00")
        try:
            dep_idx = times.index(dep_str)
        except ValueError:
            dep_idx = min(
                range(len(times)),
                key=lambda i: abs(datetime.fromisoformat(times[i]) - departure),
            )

        start = max(0, dep_idx - 6)
        end   = min(len(times) - 1, dep_idx + 6)

        hours = []
        for i in range(start, end + 1):
            t = datetime.fromisoformat(times[i])
            hours.append({
                "time":         times[i],
                "hour":         t.hour,
                "label":        t.strftime("%Hh"),
                "temperature":  round(data["temperature_2m"][i] or 0, 1),
                "wind_kmh":     round(data["windspeed_10m"][i] or 0, 1),
                "precip_mm":    round(data["precipitation"][i] or 0, 2),
                "is_departure": i == dep_idx,
            })

        return {
            "iata":         iata.upper(),
            "departure_dt": departure.isoformat(),
            "hours":        hours,
        }

    except Exception as e:
        log.warning(f"Prévisions horaires indisponibles pour {iata}: {e}")
        raise HTTPException(status_code=503, detail="Prévisions horaires non disponibles")


# Données demo : vols/jour et taux de retard par aéroport
_AIRPORT_STATS = {
    "YYZ": {"flights_today": 420, "delay_rate": 0.22},
    "YVR": {"flights_today": 280, "delay_rate": 0.19},
    "YUL": {"flights_today": 260, "delay_rate": 0.21},
    "YYC": {"flights_today": 200, "delay_rate": 0.18},
    "YEG": {"flights_today": 140, "delay_rate": 0.17},
    "YOW": {"flights_today": 130, "delay_rate": 0.20},
    "YHZ": {"flights_today":  90, "delay_rate": 0.23},
    "YWG": {"flights_today": 110, "delay_rate": 0.19},
    "YQB": {"flights_today":  80, "delay_rate": 0.21},
    "YYJ": {"flights_today":  70, "delay_rate": 0.16},
    "YQR": {"flights_today":  60, "delay_rate": 0.17},
    "YXE": {"flights_today":  55, "delay_rate": 0.18},
}

@app.get("/airports/summary")
def get_airports_summary():
    """Données statiques par aéroport — retour immédiat, sans appel externe.
    La météo temps réel est chargée à la demande via GET /weather/{iata}."""
    current_hour = datetime.now().hour
    is_peak = (7 <= current_hour <= 9) or (16 <= current_hour <= 20)

    results = []
    for airport in AIRPORTS:
        stats = _AIRPORT_STATS.get(airport["iata"], {"flights_today": 100, "delay_rate": 0.19})
        results.append({
            "iata":          airport["iata"],
            "city":          airport["city"],
            "status":        "watch" if is_peak else "ok",
            "delay_rate":    stats["delay_rate"],
            "flights_today": stats["flights_today"],
        })

    return {"airports": results, "timestamp": datetime.now().isoformat()}


@app.get("/flights/live")
def get_live_flights_over_canada():
    """Avions en vol au-dessus du Canada via OpenSky (sans authentification)."""
    try:
        resp = requests.get(
            "https://opensky-network.org/api/states/all",
            params={"lamin": 42.0, "lamax": 72.0, "lomin": -142.0, "lomax": -52.0},
            timeout=15,
        )
        resp.raise_for_status()
        states = resp.json().get("states") or []

        flights = []
        for s in states:
            lon, lat = s[5], s[6]
            if lon is None or lat is None:
                continue
            if s[8]:          # on_ground
                continue
            alt = s[13] or s[7] or 0
            if alt < 1500:    # ignore décollages/atterrissages
                continue
            flights.append({
                "icao24":     s[0],
                "callsign":   (s[1] or "").strip() or s[0],
                "lat":        round(lat, 4),
                "lon":        round(lon, 4),
                "altitude_m": round(alt),
                "velocity_ms":round(s[9] or 0),
                "heading":    round(s[10] or 0),
            })

        return {"flights": flights[:100], "count": len(flights)}

    except Exception as e:
        log.warning(f"OpenSky live error: {e}")
        return {"flights": [], "count": 0}


@app.post("/predict/timeline")
def predict_timeline(req: TimelineRequest):
    """Probabilité de retard pour chaque heure de la journée (24 inférences)."""
    if "clf" not in models:
        raise HTTPException(status_code=503, detail="Modèles non chargés")

    origin_ap = AIRPORTS_BY_IATA.get(req.origin.upper())
    weather   = get_weather_now(
        req.origin,
        origin_ap["lat"] if origin_ap else 45.0,
        origin_ap["lon"] if origin_ap else -75.0,
    )
    threshold = models["meta"]["lgbm_threshold"]

    points = []
    for hour in range(24):
        fake = PredictRequest(
            origin             = req.origin,
            destination        = req.destination,
            airline_code       = req.airline_code,
            departure_datetime = f"{req.date}T{hour:02d}:00:00",
        )
        X    = build_feature_vector(fake, weather)
        prob = float(models["clf"].predict_proba(X)[0][1])
        is_d = prob >= threshold

        if is_d:
            delay_min = float(np.expm1(models["reg"].predict(X)[0]))
            delay_min = max(0.0, round(delay_min, 1))
        else:
            delay_min = 0.0

        points.append({"hour": hour, "probability": round(prob, 4),
                        "is_delayed": is_d, "delay_minutes": delay_min})

    probs      = [p["probability"] for p in points]
    ranked     = sorted(range(24), key=lambda h: probs[h])
    best_hours = ranked[:4]
    worst_hours= ranked[-3:]

    return {"points": points, "best_hours": best_hours,
            "worst_hours": sorted(worst_hours), "threshold": threshold}


@app.post("/predict/airlines")
def predict_airlines(req: AirlinesRequest):
    """Compare les probabilités de retard par compagnie sur une route."""
    if "clf" not in models:
        raise HTTPException(status_code=503, detail="Modèles non chargés")

    origin_ap = AIRPORTS_BY_IATA.get(req.origin.upper())
    weather   = get_weather_now(
        req.origin,
        origin_ap["lat"] if origin_ap else 45.0,
        origin_ap["lon"] if origin_ap else -75.0,
    )
    threshold = models["meta"]["lgbm_threshold"]
    results   = []

    for code, name in AIRLINE_NAMES.items():
        fake = PredictRequest(
            origin             = req.origin,
            destination        = req.destination,
            airline_code       = code,
            departure_datetime = req.departure_datetime,
        )
        X    = build_feature_vector(fake, weather)
        prob = float(models["clf"].predict_proba(X)[0][1])
        is_d = prob >= threshold

        if is_d:
            delay_min = float(np.expm1(models["reg"].predict(X)[0]))
            delay_min = max(0.0, round(delay_min, 1))
        else:
            delay_min = 0.0

        results.append({"code": code, "name": name,
                         "probability": round(prob, 4),
                         "is_delayed": is_d, "delay_minutes": delay_min})

    results.sort(key=lambda r: r["probability"])
    return {"airlines": results}


@app.get("/stats/{origin}/{dest}")
def get_route_stats(origin: str, dest: str):
    """Statistiques historiques d'une route (données statiques pour démo)."""
    # En production : requête sur la DB avec les stats pré-calculées
    # Ici on retourne des valeurs illustratives
    return {
        "route":             f"{origin.upper()}-{dest.upper()}",
        "avg_delay_min":     12.4,
        "delay_rate":        0.21,
        "total_flights":     4820,
        "on_time_rate":      0.79,
        "most_delayed_hour": 18,
        "best_hour":         6,
        "note":              "Données historiques 2019-2023 BTS",
    }


@app.get("/flights/{iata}")
def get_flights(iata: str, limit: int = 10):
    """
    Vols au départ en temps réel via OpenSky Network.
    Nécessite OPENSKY_USER + OPENSKY_PASS dans .env (compte gratuit).
    """
    user = os.getenv("OPENSKY_USER")
    pwd  = os.getenv("OPENSKY_PASS")

    airport = AIRPORTS_BY_IATA.get(iata.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Aéroport {iata} non trouvé")

    if not user or not pwd:
        # Mode démo sans credentials
        return {
            "iata":    iata,
            "flights": [],
            "note":    "Ajoutez OPENSKY_USER et OPENSKY_PASS dans .env pour les vols en temps réel",
        }

    try:
        now   = int(datetime.now().timestamp())
        begin = now - 7200  # 2h en arrière

        resp = requests.get(
            "https://opensky-network.org/api/flights/departure",
            params={"airport": f"C{iata}", "begin": begin, "end": now},
            auth=(user, pwd),
            timeout=15,
        )
        resp.raise_for_status()
        flights = resp.json()[:limit]

        return {
            "iata":       iata,
            "city":       airport["city"],
            "flights":    [
                {
                    "callsign":    f.get("callsign", "").strip(),
                    "destination": f.get("estArrivalAirport", ""),
                    "departure":   datetime.fromtimestamp(f["firstSeen"]).isoformat() if f.get("firstSeen") else None,
                }
                for f in flights
            ],
            "count": len(flights),
        }

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenSky erreur: {str(e)}")
