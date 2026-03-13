"""
collect.py — Phase 1 : Collecte des données
============================================
Sources :
  - OurAirports  : coordonnées + infos aéroports canadiens
  - BTS Transtats: historique vols + retards (2019-2023)
  - Open-Meteo   : météo historique par aéroport

Usage :
  python collect.py --step airports
  python collect.py --step bts --year 2023
  python collect.py --step bts --year all
  python collect.py --step weather
  python collect.py --step all
"""

import os
import time
import argparse
import logging
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from io import StringIO

# ── Config ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR  = Path("data/raw")
PROC_DIR = Path("data/processed")

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROC_DIR.mkdir(parents=True, exist_ok=True)

# Années à collecter
YEARS = [2019, 2020, 2021, 2022, 2023]

# Aéroports canadiens principaux (code IATA → code BTS/ICAO)
CANADIAN_AIRPORTS = {
    "YYZ": {"name": "Toronto Pearson",        "lat": 43.6777, "lon": -79.6248, "province": "ON"},
    "YVR": {"name": "Vancouver Intl",          "lat": 49.1967, "lon": -123.1815,"province": "BC"},
    "YUL": {"name": "Montréal-Trudeau",        "lat": 45.4706, "lon": -73.7408, "province": "QC"},
    "YYC": {"name": "Calgary Intl",            "lat": 51.1215, "lon": -114.0127,"province": "AB"},
    "YEG": {"name": "Edmonton Intl",           "lat": 53.3097, "lon": -113.5797,"province": "AB"},
    "YOW": {"name": "Ottawa Macdonald-Cartier","lat": 45.3225, "lon": -75.6692, "province": "ON"},
    "YHZ": {"name": "Halifax Stanfield",       "lat": 44.8808, "lon": -63.5086, "province": "NS"},
    "YWG": {"name": "Winnipeg Richardson",     "lat": 49.9100, "lon": -97.2398, "province": "MB"},
    "YQB": {"name": "Québec City Jean Lesage", "lat": 46.7911, "lon": -71.3933, "province": "QC"},
    "YXE": {"name": "Saskatoon Diefenbaker",   "lat": 52.1708, "lon": -106.6997,"province": "SK"},
    "YYJ": {"name": "Victoria Intl",           "lat": 48.6469, "lon": -123.4258,"province": "BC"},
    "YQR": {"name": "Regina Intl",             "lat": 50.4319, "lon": -104.6658,"province": "SK"},
}


# ── 1. Aéroports ──────────────────────────────────────────────────
def collect_airports() -> pd.DataFrame:
    """
    Télécharge la liste complète des aéroports depuis OurAirports
    et filtre sur les aéroports canadiens importants.
    """
    log.info("📡 Téléchargement OurAirports...")
    url = "https://davidmegginson.github.io/ourairports-data/airports.csv"

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))

    # Filtre : Canada, grands aéroports
    canada = df[
        (df["iso_country"] == "CA") &
        (df["type"].isin(["large_airport", "medium_airport"])) &
        (df["iata_code"].notna()) &
        (df["iata_code"] != "")
    ].copy()

    canada = canada[[
        "iata_code", "name", "municipality",
        "latitude_deg", "longitude_deg",
        "elevation_ft", "iso_region"
    ]].rename(columns={
        "iata_code":      "iata",
        "latitude_deg":   "lat",
        "longitude_deg":  "lon",
        "elevation_ft":   "elevation",
        "iso_region":     "province",
        "municipality":   "city",
    })

    canada["province"] = canada["province"].str.replace("CA-", "")
    canada = canada.sort_values("iata").reset_index(drop=True)

    out = RAW_DIR / "airports_canada.csv"
    canada.to_csv(out, index=False)
    log.info(f"✅ {len(canada)} aéroports canadiens → {out}")
    return canada


# ── 2. Données BTS (vols historiques) ────────────────────────────
def collect_bts_year(year: int) -> pd.DataFrame:
    """
    Télécharge les données de vols depuis le BTS Transtats pour une année.
    Dataset : On-Time Reporting Carrier On-Time Performance
    URL : https://www.transtats.bts.gov/DL_SelectFields.aspx
    
    ⚠️  Le BTS ne propose pas de téléchargement direct par API publique.
        Ce script utilise les fichiers pré-téléchargés ou le miroir Kaggle.
        
    Alternative automatique : dataset Kaggle
    "Flight Delay and Cancellation Dataset (2019-2023)"
    https://www.kaggle.com/datasets/patrickzel/flight-delay-and-cancellation-dataset-2019-2023
    """
    out = RAW_DIR / f"flights_{year}.csv"

    if out.exists():
        log.info(f"⏭️  {year} déjà téléchargé, skip.")
        return pd.read_csv(out, low_memory=False)

    # ── Option A : Fichier local déjà téléchargé depuis BTS ──
    local = Path(f"data/raw/bts_{year}.csv")
    if local.exists():
        log.info(f"📂 Lecture fichier local {local}...")
        df = pd.read_csv(local, low_memory=False)
        df = clean_bts(df, year)
        df.to_csv(out, index=False)
        return df

    # ── Option B : Kaggle API ──
    log.warning(f"⚠️  Fichier BTS {year} non trouvé localement.")
    log.info("💡 Téléchargement via Kaggle API...")
    try:
        import kaggle
        kaggle.api.authenticate()
        kaggle.api.dataset_download_files(
            "patrickzel/flight-delay-and-cancellation-dataset-2019-2023",
            path=str(RAW_DIR),
            unzip=True,
        )
        log.info("✅ Dataset Kaggle téléchargé.")
        # Cherche le fichier année
        candidates = list(RAW_DIR.glob(f"*{year}*.csv"))
        if candidates:
            df = pd.read_csv(candidates[0], low_memory=False)
            df = clean_bts(df, year)
            df.to_csv(out, index=False)
            return df
    except Exception as e:
        log.error(f"❌ Kaggle échoué : {e}")
        log.info("📋 Instructions manuelles :")
        log.info("   1. Va sur https://www.transtats.bts.gov/DL_SelectFields.aspx")
        log.info("   2. Sélectionne 'Reporting Carrier On-Time Performance'")
        log.info(f"   3. Filtre sur l'année {year}, tous les mois")
        log.info(f"   4. Sauvegarde sous data/raw/bts_{year}.csv")
        raise FileNotFoundError(f"Données BTS {year} introuvables.")


def clean_bts(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Nettoyage et standardisation des colonnes BTS.
    """
    log.info(f"🧹 Nettoyage BTS {year} ({len(df):,} lignes)...")

    # Colonnes à garder (noms BTS standard)
    keep = [
        "FL_DATE", "OP_CARRIER", "TAIL_NUM",
        "ORIGIN", "DEST",
        "CRS_DEP_TIME", "DEP_TIME", "DEP_DELAY",
        "CRS_ARR_TIME", "ARR_TIME", "ARR_DELAY",
        "CANCELLED", "CANCELLATION_CODE",
        "AIR_TIME", "DISTANCE",
        "CARRIER_DELAY", "WEATHER_DELAY",
        "NAS_DELAY", "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY",
    ]

    # Garde seulement les colonnes disponibles
    available = [c for c in keep if c in df.columns]
    df = df[available].copy()

    # Renommage standardisé
    df.columns = [c.lower() for c in df.columns]

    # Types
    df["fl_date"]   = pd.to_datetime(df["fl_date"], errors="coerce")
    df["dep_delay"] = pd.to_numeric(df["dep_delay"], errors="coerce")
    df["arr_delay"] = pd.to_numeric(df["arr_delay"], errors="coerce")
    df["distance"]  = pd.to_numeric(df["distance"],  errors="coerce")
    df["cancelled"] = pd.to_numeric(df["cancelled"], errors="coerce").fillna(0).astype(int)

    # Features temporelles de base
    df["year"]        = df["fl_date"].dt.year
    df["month"]       = df["fl_date"].dt.month
    df["day_of_week"] = df["fl_date"].dt.dayofweek   # 0=lundi
    df["day_of_year"] = df["fl_date"].dt.dayofyear

    # Heure de départ (HHMM → heure décimale)
    df["dep_hour"] = df["crs_dep_time"].apply(
        lambda x: int(str(int(x)).zfill(4)[:2]) if pd.notna(x) else np.nan
    )

    # Cible binaire : retardé si dep_delay >= 15 min
    df["is_delayed"] = ((df["dep_delay"] >= 15) & (df["cancelled"] == 0)).astype(int)

    # Retard positif seulement (pour régression)
    df["delay_minutes"] = df["dep_delay"].clip(lower=0)

    # Supprime vols sans info de retard (sauf annulés)
    df = df[df["cancelled"] == 1 | df["dep_delay"].notna()].copy()

    log.info(f"   → {len(df):,} lignes après nettoyage")
    log.info(f"   → Taux retard : {df['is_delayed'].mean():.1%}")
    return df


def collect_bts_all() -> None:
    """Collecte toutes les années définies dans YEARS."""
    dfs = []
    for year in YEARS:
        try:
            df = collect_bts_year(year)
            dfs.append(df)
            log.info(f"✅ {year} : {len(df):,} vols")
        except FileNotFoundError as e:
            log.warning(str(e))

    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        out = PROC_DIR / "flights_all.csv"
        combined.to_csv(out, index=False)
        log.info(f"\n📦 Dataset combiné : {len(combined):,} vols → {out}")
        print_stats(combined)


def print_stats(df: pd.DataFrame) -> None:
    """Affiche un résumé statistique du dataset."""
    print("\n" + "="*50)
    print("📊 STATISTIQUES DATASET")
    print("="*50)
    print(f"Total vols       : {len(df):>12,}")
    print(f"Vols retardés    : {df['is_delayed'].sum():>12,} ({df['is_delayed'].mean():.1%})")
    print(f"Vols annulés     : {df['cancelled'].sum():>12,} ({df['cancelled'].mean():.1%})")
    print(f"Retard moyen     : {df.loc[df['dep_delay']>0,'dep_delay'].mean():>11.1f} min")
    print(f"Retard médian    : {df.loc[df['dep_delay']>0,'dep_delay'].median():>11.1f} min")
    print(f"Années           : {sorted(df['year'].unique())}")
    print(f"Compagnies       : {df['op_carrier'].nunique()}")
    print(f"Aéroports origine: {df['origin'].nunique()}")
    print("="*50 + "\n")


# ── 3. Météo (Open-Meteo) ─────────────────────────────────────────
def collect_weather_airport(
    iata: str,
    lat: float,
    lon: float,
    start: str = "2019-01-01",
    end:   str = "2023-12-31",
    max_retries: int = 5,
) -> pd.DataFrame:
    """
    Télécharge la météo horaire depuis Open-Meteo pour un aéroport.
    Gratuit, sans clé API. Retry automatique sur 429.
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":        lat,
        "longitude":       lon,
        "start_date":      start,
        "end_date":        end,
        "hourly":          [
            "temperature_2m",
            "precipitation",
            "windspeed_10m",
            "winddirection_10m",
            "visibility",
            "cloudcover",
            "snowfall",
            "weathercode",
        ],
        "timezone":        "America/Toronto",
        "windspeed_unit":  "kmh",
    }

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)  # 30s, 60s, 90s...
                log.warning(f"   ⏳ Rate limit — attente {wait}s avant retry ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    else:
        raise Exception(f"Échec après {max_retries} tentatives pour {iata}")

    hourly = data["hourly"]
    df = pd.DataFrame({
        "datetime":    pd.to_datetime(hourly["time"]),
        "temperature": hourly["temperature_2m"],
        "precip_mm":   hourly["precipitation"],
        "wind_kmh":    hourly["windspeed_10m"],
        "wind_dir":    hourly["winddirection_10m"],
        "visibility":  hourly["visibility"],
        "cloud_pct":   hourly["cloudcover"],
        "snowfall_cm": hourly["snowfall"],
        "weather_code":hourly["weathercode"],
    })

    df["airport"] = iata
    df["date"]    = df["datetime"].dt.date
    df["hour"]    = df["datetime"].dt.hour

    # Indicateur météo adverse
    df["bad_weather"] = (
        (df["wind_kmh"] > 40) |
        (df["precip_mm"] > 5) |
        (df["visibility"] < 1000) |
        (df["snowfall_cm"] > 2)
    ).astype(int)

    return df


def collect_weather_all() -> None:
    """Collecte la météo pour tous les aéroports canadiens principaux."""
    airports_file = RAW_DIR / "airports_canada.csv"

    if not airports_file.exists():
        log.warning("⚠️  airports_canada.csv non trouvé, collecte d'abord les aéroports.")
        collect_airports()

    airports = pd.read_csv(airports_file)

    # Filtre sur nos aéroports principaux
    main = airports[airports["iata"].isin(CANADIAN_AIRPORTS.keys())]

    all_weather = []
    for _, row in main.iterrows():
        iata = row["iata"]
        out  = RAW_DIR / f"weather_{iata}.csv"

        if out.exists():
            log.info(f"⏭️  Météo {iata} déjà collectée, skip.")
            all_weather.append(pd.read_csv(out))
            continue

        log.info(f"🌤️  Collecte météo {iata} ({row['name']})...")
        try:
            df = collect_weather_airport(iata, row["lat"], row["lon"])
            df.to_csv(out, index=False)
            all_weather.append(df)
            log.info(f"   ✅ {len(df):,} entrées horaires")
            time.sleep(15)  # Respecte le rate limit Open-Meteo
        except Exception as e:
            log.error(f"   ❌ Erreur {iata} : {e}")

    if all_weather:
        combined = pd.concat(all_weather, ignore_index=True)
        out = PROC_DIR / "weather_all.csv"
        combined.to_csv(out, index=False)
        log.info(f"\n📦 Météo combinée : {len(combined):,} entrées → {out}")


# ── CLI ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Collecte données Flight Delay Predictor")
    parser.add_argument(
        "--step",
        choices=["airports", "bts", "weather", "all"],
        default="all",
        help="Étape à exécuter",
    )
    parser.add_argument(
        "--year",
        default="all",
        help="Année BTS (2019-2023) ou 'all'",
    )
    args = parser.parse_args()

    log.info("🚀 Démarrage collecte de données")
    log.info(f"   Step  : {args.step}")
    log.info(f"   Year  : {args.year}")
    print()

    if args.step in ("airports", "all"):
        collect_airports()

    if args.step in ("bts", "all"):
        if args.year == "all":
            collect_bts_all()
        else:
            year = int(args.year)
            df = collect_bts_year(year)
            print_stats(df)

    if args.step in ("weather", "all"):
        collect_weather_all()

    log.info("\n✅ Collecte terminée !")


if __name__ == "__main__":
    main()
