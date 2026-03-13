"""
features.py — Phase 2 : Feature Engineering
=============================================
Input  : data/raw/flights_sample_3m.csv + data/processed/weather_all.csv
Output : data/features/features.parquet

Features produites :
  - Temporelles    : heure, jour semaine, mois, saison, week-end
  - Compagnie      : encodage + historique retards par compagnie
  - Route          : origine→dest + historique retards par route
  - Propagation    : retard vol précédent (tail number)
  - Météo          : température, vent, précip, visibilité à l'origine
  - Cibles         : is_delayed (classification), delay_minutes (régression)

Usage :
  uv run python features.py
  uv run python features.py --sample 100000  ← test rapide
"""

import argparse
import logging
import warnings
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR      = Path("data/raw")
PROC_DIR     = Path("data/processed")
FEATURES_DIR = Path("data/features")
FEATURES_DIR.mkdir(parents=True, exist_ok=True)


# ── 1. Chargement & nettoyage de base ────────────────────────────
def load_flights(sample: int = None) -> pd.DataFrame:
    path = RAW_DIR / "flights_sample_3m.csv"
    log.info(f"📂 Chargement {path}...")

    dtype = {
        "AIRLINE_CODE":        "category",
        "ORIGIN":              "category",
        "DEST":                "category",
        "CANCELLATION_CODE":   "category",
    }

    df = pd.read_csv(path, dtype=dtype, low_memory=False)

    if sample:
        df = df.sample(n=min(sample, len(df)), random_state=42).copy()
        log.info(f"🔬 Mode test : {len(df):,} lignes")

    log.info(f"✅ {len(df):,} vols chargés — {df.shape[1]} colonnes")
    return df


def basic_clean(df: pd.DataFrame) -> pd.DataFrame:
    log.info("🧹 Nettoyage de base...")

    # Dates
    df["FL_DATE"] = pd.to_datetime(df["FL_DATE"], errors="coerce")

    # Numériques
    num_cols = [
        "DEP_DELAY", "ARR_DELAY", "DISTANCE",
        "CRS_ELAPSED_TIME", "AIR_TIME",
        "TAXI_OUT", "TAXI_IN",
        "DELAY_DUE_CARRIER", "DELAY_DUE_WEATHER",
        "DELAY_DUE_NAS", "DELAY_DUE_SECURITY", "DELAY_DUE_LATE_AIRCRAFT",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Flags
    df["CANCELLED"] = pd.to_numeric(df["CANCELLED"], errors="coerce").fillna(0).astype(int)
    df["DIVERTED"]  = pd.to_numeric(df["DIVERTED"],  errors="coerce").fillna(0).astype(int)

    # Supprime vols sans date ou sans info retard (non annulés)
    before = len(df)
    df = df[df["FL_DATE"].notna()].copy()
    df = df[(df["CANCELLED"] == 1) | df["DEP_DELAY"].notna()].copy()
    log.info(f"   Supprimé {before - len(df):,} lignes invalides → {len(df):,} restantes")

    return df


# ── 2. Features temporelles ───────────────────────────────────────
def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info("⏰ Features temporelles...")

    df["year"]         = df["FL_DATE"].dt.year
    df["month"]        = df["FL_DATE"].dt.month
    df["day_of_week"]  = df["FL_DATE"].dt.dayofweek   # 0=lundi, 6=dimanche
    df["day_of_year"]  = df["FL_DATE"].dt.dayofyear
    df["week_of_year"] = df["FL_DATE"].dt.isocalendar().week.astype(int)

    # Heure départ planifié (HHMM → heure entière 0-23)
    df["dep_hour"] = df["CRS_DEP_TIME"].apply(
        lambda x: int(str(int(x)).zfill(4)[:2]) if pd.notna(x) and x > 0 else np.nan
    )

    # Saison
    df["season"] = df["month"].map({
        12: "winter", 1: "winter", 2: "winter",
        3:  "spring", 4: "spring", 5: "spring",
        6:  "summer", 7: "summer", 8: "summer",
        9:  "fall",   10: "fall",  11: "fall",
    })

    # Périodes de la journée
    df["time_of_day"] = pd.cut(
        df["dep_hour"],
        bins=[-1, 5, 11, 16, 20, 24],
        labels=["night", "morning", "afternoon", "evening", "late_night"],
    )

    # Indicateurs binaires
    df["is_weekend"]  = (df["day_of_week"] >= 5).astype(int)
    df["is_holiday_season"] = (
        ((df["month"] == 12) & (df["FL_DATE"].dt.day >= 20)) |
        ((df["month"] == 1)  & (df["FL_DATE"].dt.day <= 5)) |
        ((df["month"] == 7))   # été
    ).astype(int)

    # Encodage cyclique heure (pour capturer la circularité 23h→0h)
    df["dep_hour_sin"] = np.sin(2 * np.pi * df["dep_hour"] / 24)
    df["dep_hour_cos"] = np.cos(2 * np.pi * df["dep_hour"] / 24)

    # Encodage cyclique mois
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Encodage cyclique jour de semaine
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    return df


# ── 3. Features compagnie ─────────────────────────────────────────
def add_airline_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info("✈️  Features compagnie...")

    # Taux de retard historique par compagnie (leave-one-out sur train)
    airline_stats = (
        df[df["CANCELLED"] == 0]
        .groupby("AIRLINE_CODE")["DEP_DELAY"]
        .agg(
            airline_avg_delay="mean",
            airline_delay_rate=lambda x: (x >= 15).mean(),
            airline_flight_count="count",
        )
        .reset_index()
    )
    airline_stats.columns = ["AIRLINE_CODE", "airline_avg_delay", "airline_delay_rate", "airline_flight_count"]

    df = df.merge(airline_stats, on="AIRLINE_CODE", how="left")

    # Taille compagnie (proxy pour fiabilité)
    total = airline_stats["airline_flight_count"].sum()
    df["airline_market_share"] = df["airline_flight_count"] / total

    return df


# ── 4. Features route ─────────────────────────────────────────────
def add_route_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info("🗺️  Features route...")

    df["route"] = df["ORIGIN"].astype(str) + "_" + df["DEST"].astype(str)

    route_stats = (
        df[df["CANCELLED"] == 0]
        .groupby("route")["DEP_DELAY"]
        .agg(
            route_avg_delay="mean",
            route_delay_rate=lambda x: (x >= 15).mean(),
            route_flight_count="count",
        )
        .reset_index()
    )
    route_stats.columns = ["route", "route_avg_delay", "route_delay_rate", "route_flight_count"]

    df = df.merge(route_stats, on="route", how="left")

    # Stats par aéroport d'origine
    origin_stats = (
        df[df["CANCELLED"] == 0]
        .groupby("ORIGIN")["DEP_DELAY"]
        .agg(
            origin_avg_delay="mean",
            origin_delay_rate=lambda x: (x >= 15).mean(),
        )
        .reset_index()
    )
    origin_stats.columns = ["ORIGIN", "origin_avg_delay", "origin_delay_rate"]
    df = df.merge(origin_stats, on="ORIGIN", how="left")

    # Stats par aéroport de destination
    dest_stats = (
        df[df["CANCELLED"] == 0]
        .groupby("DEST")["ARR_DELAY"]
        .agg(
            dest_avg_arr_delay="mean",
        )
        .reset_index()
    )
    dest_stats.columns = ["DEST", "dest_avg_arr_delay"]
    df = df.merge(dest_stats, on="DEST", how="left")

    return df


# ── 5. Feature propagation (retard vol précédent) ─────────────────
def add_propagation_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info("🔄 Features propagation (tail number)...")

    if "FL_NUMBER" not in df.columns or "AIRLINE_CODE" not in df.columns:
        log.warning("   Colonnes manquantes pour propagation, skip.")
        return df

    # Crée une clé avion unique
    df["tail_key"] = df["AIRLINE_CODE"].astype(str) + "_" + df["FL_NUMBER"].astype(str)

    # Trie par avion + date + heure
    df = df.sort_values(["tail_key", "FL_DATE", "CRS_DEP_TIME"]).copy()

    # Retard du vol précédent du même avion
    df["prev_dep_delay"] = df.groupby("tail_key")["DEP_DELAY"].shift(1)

    # Retard moyen des 3 derniers vols de l'avion
    df["prev_3_avg_delay"] = (
        df.groupby("tail_key")["DEP_DELAY"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )

    # Flag : l'avion précédent était retardé
    df["prev_was_delayed"] = (df["prev_dep_delay"] >= 15).astype(float)

    # Remplit les NaN (premier vol de l'avion) par 0
    df["prev_dep_delay"]   = df["prev_dep_delay"].fillna(0)
    df["prev_3_avg_delay"] = df["prev_3_avg_delay"].fillna(0)
    df["prev_was_delayed"] = df["prev_was_delayed"].fillna(0)

    return df


# ── 6. Features météo ─────────────────────────────────────────────
def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    weather_path = PROC_DIR / "weather_all.csv"

    if not weather_path.exists():
        log.warning("⚠️  weather_all.csv non trouvé — features météo ignorées.")
        log.info("   Lance d'abord : uv run python collect.py --step weather")
        # Features météo par défaut à 0
        for col in ["temperature", "wind_kmh", "precip_mm", "visibility", "bad_weather", "snowfall_cm"]:
            df[col] = 0.0
        return df

    log.info("🌤️  Merge features météo...")
    weather = pd.read_csv(weather_path)
    weather["date"]    = pd.to_datetime(weather["date"]).dt.date
    weather["airport"] = weather["airport"].astype(str)

    # Agrège par aéroport + date + heure
    w_hourly = weather.groupby(["airport", "date", "hour"]).agg(
        temperature=("temperature", "mean"),
        wind_kmh=("wind_kmh", "mean"),
        precip_mm=("precip_mm", "sum"),
        visibility=("visibility", "mean"),
        bad_weather=("bad_weather", "max"),
        snowfall_cm=("snowfall_cm", "sum"),
    ).reset_index()

    # Prépare clés de jointure dans df
    df["_date"]     = df["FL_DATE"].dt.date
    df["_dep_hour"] = df["dep_hour"].fillna(12).astype(int)
    df["_origin"]   = df["ORIGIN"].astype(str)

    df = df.merge(
        w_hourly.rename(columns={"airport": "_origin", "date": "_date", "hour": "_dep_hour"}),
        on=["_origin", "_date", "_dep_hour"],
        how="left",
    )

    # Remplit les NaN météo par médianes
    for col in ["temperature", "wind_kmh", "precip_mm", "visibility", "snowfall_cm"]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    df["bad_weather"] = df["bad_weather"].fillna(0).astype(int)

    df.drop(columns=["_date", "_dep_hour", "_origin"], inplace=True, errors="ignore")

    log.info("   ✅ Features météo ajoutées")
    return df


# ── 7. Cibles ─────────────────────────────────────────────────────
def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    log.info("🎯 Création des cibles...")

    # Classification : retardé si DEP_DELAY >= 15 min (standard industrie)
    df["is_delayed"] = (
        (df["DEP_DELAY"] >= 15) & (df["CANCELLED"] == 0)
    ).astype(int)

    # Régression : minutes de retard (0 si à l'heure ou en avance)
    df["delay_minutes"] = df["DEP_DELAY"].clip(lower=0).fillna(0)

    # Stats
    n_total    = len(df)
    n_delayed  = df["is_delayed"].sum()
    n_cancel   = df["CANCELLED"].sum()
    avg_delay  = df.loc[df["delay_minutes"] > 0, "delay_minutes"].mean()

    log.info(f"   Total vols    : {n_total:,}")
    log.info(f"   Retardés      : {n_delayed:,} ({n_delayed/n_total:.1%})")
    log.info(f"   Annulés       : {n_cancel:,}  ({n_cancel/n_total:.1%})")
    log.info(f"   Retard moyen  : {avg_delay:.1f} min (quand retardé)")

    return df


# ── 8. Sélection finale des features ─────────────────────────────
FEATURE_COLS = [
    # Temporelles
    "dep_hour", "dep_hour_sin", "dep_hour_cos",
    "day_of_week", "dow_sin", "dow_cos",
    "month", "month_sin", "month_cos",
    "year", "is_weekend", "is_holiday_season",
    # Compagnie
    "AIRLINE_CODE",
    "airline_avg_delay", "airline_delay_rate", "airline_market_share",
    # Route
    "ORIGIN", "DEST",
    "route_avg_delay", "route_delay_rate",
    "origin_avg_delay", "origin_delay_rate",
    "dest_avg_arr_delay",
    "DISTANCE",
    # Propagation
    "prev_dep_delay", "prev_3_avg_delay", "prev_was_delayed",
    # Météo
    "temperature", "wind_kmh", "precip_mm", "visibility", "bad_weather", "snowfall_cm",
    # Cibles
    "is_delayed", "delay_minutes",
    # Méta (pas features mais utiles pour debug)
    "FL_DATE", "AIRLINE", "FL_NUMBER", "ORIGIN_CITY", "DEST_CITY", "CANCELLED",
]


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    available = [c for c in FEATURE_COLS if c in df.columns]
    missing   = [c for c in FEATURE_COLS if c not in df.columns]

    if missing:
        log.warning(f"   Colonnes manquantes ignorées : {missing}")

    return df[available].copy()


# ── Main ──────────────────────────────────────────────────────────
def main(sample: int = None):
    log.info("🚀 Démarrage feature engineering")
    print()

    df = load_flights(sample=sample)
    df = basic_clean(df)
    df = add_temporal_features(df)
    df = add_airline_features(df)
    df = add_route_features(df)
    df = add_propagation_features(df)
    df = add_weather_features(df)
    df = add_targets(df)
    df = select_features(df)

    # Sauvegarde en parquet (plus rapide + léger que CSV)
    out = FEATURES_DIR / "features.parquet"
    df.to_parquet(out, index=False)
    log.info(f"\n💾 Features sauvegardées → {out}")
    log.info(f"   Shape : {df.shape[0]:,} lignes × {df.shape[1]} colonnes")

    # Aperçu
    print("\n📊 Aperçu des features :")
    print(df.describe().round(2).to_string())
    print(f"\n✅ Colonnes finales :\n{df.columns.tolist()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None,
                        help="Nombre de lignes pour test rapide (ex: 100000)")
    args = parser.parse_args()
    main(sample=args.sample)
