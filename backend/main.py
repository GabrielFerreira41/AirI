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

class PredictResponse(BaseModel):
    is_delayed: bool
    delay_probability: float
    delay_minutes: float
    confidence: str              # "high" / "medium" / "low"
    threshold_used: float
    features_used: dict


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #
def get_weather_now(iata: str, lat: float, lon: float) -> dict:
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
        resp = requests.get(url, params=params, timeout=10)
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
            "dep_hour":    datetime.fromisoformat(req.departure_datetime).hour,
            "is_weekend":  int(datetime.fromisoformat(req.departure_datetime).weekday() >= 5),
        },
    )


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
