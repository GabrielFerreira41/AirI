# ✈️ Flight Delay Predictor

Application full-stack de prédiction de retards de vols au départ du Canada.  
Carte interactive + modèle ML (classification + régression) + API Python.

---

## 🎯 Objectif

Permettre à un utilisateur de sélectionner un aéroport canadien, de choisir un vol au départ, et d'obtenir :
- **Une probabilité de retard** (classification binaire ≥15 min)
- **Une estimation en minutes** si le vol est prédit comme retardé (régression)

---

## 🏗️ Architecture

```
flight-delay-predictor/
│
├── frontend/                   ← Next.js 14 (App Router)
│   ├── app/
│   │   ├── page.tsx            ← Page principale avec carte
│   │   └── api/                ← Proxy vers FastAPI si besoin
│   ├── components/
│   │   ├── Map.tsx             ← Carte interactive (Leaflet/Mapbox)
│   │   ├── AirportMarker.tsx   ← Marqueur aéroport cliquable
│   │   ├── FlightPanel.tsx     ← Panel liste des vols
│   │   └── PredictionCard.tsx  ← Résultat de prédiction
│   └── lib/
│       └── api.ts              ← Appels vers le backend
│
├── backend/                    ← FastAPI (Python 3.11+)
│   ├── main.py                 ← Entry point + CORS
│   ├── routers/
│   │   ├── airports.py         ← GET /airports
│   │   ├── flights.py          ← GET /flights/{airport_code}
│   │   ├── predict.py          ← POST /predict
│   │   ├── weather.py          ← GET /weather/{airport_code}
│   │   └── stats.py            ← GET /stats/{route}
│   ├── models/
│   │   └── predictor.py        ← Chargement + inférence ML
│   ├── services/
│   │   ├── opensky.py          ← API OpenSky (vols live)
│   │   ├── weather.py          ← API Open-Meteo (météo)
│   │   └── cache.py            ← Cache Redis/mémoire
│   └── requirements.txt
│
└── ml/                         ← Pipeline ML (Jupyter + scripts)
    ├── notebooks/
    │   ├── 01_data_collection.ipynb
    │   ├── 02_eda.ipynb
    │   ├── 03_feature_engineering.ipynb
    │   ├── 04_training.ipynb
    │   └── 05_evaluation.ipynb
    ├── data/
    │   ├── raw/                ← Données brutes BTS + météo
    │   ├── processed/          ← Données nettoyées
    │   └── features/           ← Features finales
    ├── models/
    │   ├── classifier.joblib   ← Modèle classification exporté
    │   └── regressor.joblib    ← Modèle régression exporté
    ├── src/
    │   ├── collect.py          ← Script collecte données
    │   ├── features.py         ← Feature engineering
    │   └── train.py            ← Entraînement + export
    └── requirements.txt
```

---

## 🧠 Modèle ML

### Features utilisées

| Feature | Type | Source |
|---|---|---|
| `hour`, `day_of_week`, `month` | Temporel | BTS |
| `airline` | Catégoriel | BTS |
| `origin`, `destination` | Catégoriel | BTS |
| `distance` | Numérique | BTS |
| `temperature`, `wind_speed`, `precipitation`, `visibility` | Météo | Open-Meteo |
| `avg_delay_route` | Historique | BTS agrégé |
| `avg_delay_airline` | Historique | BTS agrégé |
| `prev_flight_delay` | Propagation | BTS (tail number) |

### Modèles

```
Classification  →  LightGBM (retardé oui/non, seuil 15 min)
                   Métrique cible : ROC-AUC, F1
Régression      →  XGBoost  (durée du retard en minutes)
                   Métrique cible : RMSE, MAE
```

### Pipeline d'entraînement

```
BTS Data (CSV)
    ↓ collect.py
Données brutes
    ↓ features.py
Features engineered
    ↓ train.py (Optuna tuning + W&B tracking)
classifier.joblib + regressor.joblib
    ↓
backend/models/
```

---

## 🗺️ Frontend

### Carte interactive

- Aéroports canadiens affichés comme marqueurs
- Clic sur un aéroport → liste des vols en départ
- Clic sur un vol → panel de prédiction

### Panel de prédiction

```
Vol AC123 — YUL → JFK
Départ : 14h35 | Air Canada

Probabilité de retard : 73%  ████████░░
Retard estimé          : ~28 min

Facteurs :
  ⚠️ Météo : vents forts (42 km/h)
  ⚠️ Route historiquement chargée
  ✅ Compagnie : bonne ponctualité
```

---

## ⚙️ Backend — Endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/airports` | Liste des aéroports canadiens (code, nom, lat/lng) |
| `GET` | `/flights/{code}` | Vols en départ d'un aéroport (live via OpenSky) |
| `POST` | `/predict` | Prédiction retard (classification + régression) |
| `GET` | `/weather/{code}` | Météo live à l'aéroport |
| `GET` | `/stats/{route}` | Historique retards sur une route |

### Exemple requête `/predict`

```json
POST /predict
{
  "flight_number": "AC123",
  "airline": "Air Canada",
  "origin": "YUL",
  "destination": "JFK",
  "scheduled_departure": "2026-05-15T14:35:00",
  "distance_km": 533
}
```

```json
Response
{
  "delayed_probability": 0.73,
  "estimated_delay_minutes": 28,
  "is_delayed": true,
  "confidence": "high",
  "factors": ["weather_wind", "route_history"]
}
```

---

## 🗄️ Sources de données

| Source | Usage | Accès |
|---|---|---|
| [BTS Transtats](https://www.transtats.bts.gov) | Historique vols + retards | Gratuit (CSV) |
| [Open-Meteo](https://open-meteo.com) | Météo historique + prévisions | Gratuit, sans clé |
| [OpenSky Network](https://opensky-network.org) | Vols en temps réel | Gratuit (compte) |
| [OurAirports](https://ourairports.com/data/) | Coordonnées aéroports | Gratuit (CSV) |

---

## 🚀 Stack technique

### Frontend
- Next.js 14 (App Router)
- TypeScript + Tailwind CSS
- Leaflet.js / Mapbox GL (carte)
- Recharts (graphiques)

### Backend
- FastAPI (Python 3.11+)
- Pydantic (validation)
- httpx (appels API externes)
- Redis (cache optionnel)

### ML
- LightGBM + XGBoost
- scikit-learn (preprocessing, pipeline)
- pandas + numpy
- Optuna (hyperparameter tuning)
- Weights & Biases (experiment tracking)
- joblib (export modèles)

---

## 📅 Plan de développement

| Phase | Contenu | Durée estimée |
|---|---|---|
| **1. Data** | Collecte BTS, nettoyage, feature engineering | 3–4 jours |
| **2. ML** | EDA, entraînement, évaluation, export | 3–4 jours |
| **3. Backend** | FastAPI + endpoints + intégration modèle | 2–3 jours |
| **4. Frontend** | Carte + UI prédiction + connexion API | 3–4 jours |
| **5. Deploy** | Vercel (frontend) + Railway (backend) | 1–2 jours |

**Total estimé : 2–3 semaines**

---

## 🌐 Déploiement

```
Frontend  →  Vercel       (Next.js)
Backend   →  Railway      (FastAPI + modèles)
Modèles   →  inclus dans le container Railway
```

Variables d'environnement nécessaires :

```env
# Frontend (.env.local)
NEXT_PUBLIC_API_URL=https://your-api.railway.app
NEXT_PUBLIC_MAPBOX_TOKEN=pk.xxx   # si Mapbox

# Backend (.env)
OPENSKY_USERNAME=xxx
OPENSKY_PASSWORD=xxx
```

---

## 📊 Métriques cibles

| Modèle | Métrique | Cible |
|---|---|---|
| Classification | ROC-AUC | > 0.80 |
| Classification | F1-score | > 0.72 |
| Régression | RMSE | < 20 min |
| Régression | MAE | < 14 min |

---

## 👤 Auteur

**Gabriel Ferreira** — Maîtrise Informatique (IA), Université de Montréal  
[GitHub](https://github.com/GabrielFerreira41) · [LinkedIn](https://www.linkedin.com/in/gabriel-ferreira-udem/) · [Portfolio](https://gabrielferreiramtl.vercel.app)