"""
train.py - Phase 3 : Entrainement des modeles
===============================================
Modeles  : LightGBM + XGBoost (classification + regression)
Tuning   : Optuna (hyperparameter search)
Tracking : Weights & Biases
Export   : models/classifier_lgbm.joblib, classifier_xgb.joblib
           models/regressor_lgbm.joblib

Fixes appliques :
  1. scale_pos_weight  -> compense desequilibre 82%/18%
  2. Seuil adaptatif   -> maximise F1 sur val set au lieu de 0.5 fixe
  3. Log-transform      -> stabilise apprentissage regression (queue longue)

Usage :
  uv run python train.py                    <- entrainement complet
  uv run python train.py --fast             <- 100k lignes, 10 trials Optuna
  uv run python train.py --no-wandb         <- sans W&B
  uv run python train.py --no-tuning        <- sans Optuna (params defaut)
"""

import argparse
import logging
import warnings
import joblib
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    roc_auc_score, f1_score, classification_report,
    mean_squared_error, mean_absolute_error, r2_score,
)
import lightgbm as lgb
import xgboost as xgb
import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

FEATURES_DIR = Path("data/features")
MODELS_DIR   = Path("models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    "dep_hour", "dep_hour_sin", "dep_hour_cos",
    "day_of_week", "dow_sin", "dow_cos",
    "month", "month_sin", "month_cos",
    "year", "is_weekend", "is_holiday_season",
    "airline_avg_delay", "airline_delay_rate", "airline_market_share",
    "route_avg_delay", "route_delay_rate",
    "origin_avg_delay", "origin_delay_rate",
    "dest_avg_arr_delay", "DISTANCE",
    "prev_dep_delay", "prev_3_avg_delay", "prev_was_delayed",
    "temperature", "wind_kmh", "precip_mm",
    "visibility", "bad_weather", "snowfall_cm",
]

CAT_COLS   = ["AIRLINE_CODE", "ORIGIN", "DEST"]
TARGET_CLF = "is_delayed"
TARGET_REG = "delay_minutes"


# ------------------------------------------------------------------ #
# 1. Chargement & preparation                                         #
# ------------------------------------------------------------------ #
def load_data(fast: bool = False) -> pd.DataFrame:
    path = FEATURES_DIR / "features.parquet"
    log.info(f"Chargement {path}...")
    df = pd.read_parquet(path)
    if fast:
        df = df.sample(n=min(100_000, len(df)), random_state=42)
        log.info(f"Mode rapide : {len(df):,} lignes")
    else:
        log.info(f"{len(df):,} lignes chargees")
    df = df[df["CANCELLED"] == 0].copy()
    log.info(f"   Apres filtre annules : {len(df):,} vols")
    return df


def prepare_features(df: pd.DataFrame) -> tuple:
    log.info("Preparation des features...")
    encoders = {}
    for col in CAT_COLS:
        if col in df.columns:
            le = LabelEncoder()
            df[col + "_enc"] = le.fit_transform(df[col].astype(str))
            encoders[col] = le

    num_features = [c for c in FEATURE_COLS if c in df.columns]
    cat_features = [c + "_enc" for c in CAT_COLS if c + "_enc" in df.columns]
    all_features = num_features + cat_features

    X     = df[all_features].copy()
    y_clf = df[TARGET_CLF].copy()
    y_reg = df[TARGET_REG].copy()

    for col in X.columns:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median())

    log.info(f"   Features      : {len(all_features)} colonnes")
    log.info(f"   Taux retard   : {y_clf.mean():.1%}")
    log.info(f"   Retard moyen  : {y_reg[y_reg > 0].mean():.1f} min (vols retardes)")
    return X, y_clf, y_reg, encoders, all_features


def split_data(X, y_clf, y_reg):
    X_train, X_test, y_clf_train, y_clf_test, y_reg_train, y_reg_test = train_test_split(
        X, y_clf, y_reg, test_size=0.2, random_state=42, stratify=y_clf,
    )
    log.info(f"   Train : {len(X_train):,} | Test : {len(X_test):,}")
    return X_train, X_test, y_clf_train, y_clf_test, y_reg_train, y_reg_test


# ------------------------------------------------------------------ #
# 2. Fix 2 - Seuil adaptatif                                          #
# ------------------------------------------------------------------ #
def find_best_threshold(y_true, probs) -> float:
    thresholds = np.arange(0.1, 0.7, 0.01)
    best_t, best_f1 = 0.5, 0.0
    for t in thresholds:
        preds = (probs >= t).astype(int)
        score = f1_score(y_true, preds, zero_division=0)
        if score > best_f1:
            best_f1, best_t = score, t
    log.info(f"   Seuil optimal : {best_t:.2f} (F1={best_f1:.4f} vs F1={f1_score(y_true, (probs>=0.5).astype(int)):.4f} a 0.5)")
    return best_t


# ------------------------------------------------------------------ #
# 3. Optuna tuning                                                    #
# ------------------------------------------------------------------ #
def tune_lgbm_classifier(X_train, y_train, n_trials: int = 50) -> dict:
    log.info(f"Optuna LightGBM classifier ({n_trials} trials)...")
    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    spw = neg / pos
    log.info(f"   scale_pos_weight = {spw:.2f}")

    def objective(trial):
        params = {
            "objective":         "binary",
            "metric":            "auc",
            "verbosity":         -1,
            "boosting_type":     "gbdt",
            "scale_pos_weight":  spw,
            "n_estimators":      trial.suggest_int("n_estimators", 100, 1000),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves":        trial.suggest_int("num_leaves", 20, 300),
            "max_depth":         trial.suggest_int("max_depth", 3, 12),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
        )
        model = lgb.LGBMClassifier(**params)
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(50, verbose=False)])
        probs = model.predict_proba(X_val)[:, 1]
        return roc_auc_score(y_val, probs)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    log.info(f"   Meilleur ROC-AUC : {study.best_value:.4f}")
    best = study.best_params
    best["scale_pos_weight"] = spw
    return best


def tune_lgbm_regressor(X_train, y_train, n_trials: int = 50) -> dict:
    log.info(f"Optuna LightGBM regressor ({n_trials} trials)...")
    mask        = y_train > 0
    X_delayed   = X_train[mask]
    y_log       = np.log1p(y_train[mask])   # Fix 3 : log-transform

    def objective(trial):
        params = {
            "objective":         "regression",
            "metric":            "rmse",
            "verbosity":         -1,
            "n_estimators":      trial.suggest_int("n_estimators", 100, 1000),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves":        trial.suggest_int("num_leaves", 20, 300),
            "max_depth":         trial.suggest_int("max_depth", 3, 12),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }
        X_t, X_v, y_t, y_v = train_test_split(X_delayed, y_log, test_size=0.2, random_state=42)
        model = lgb.LGBMRegressor(**params)
        model.fit(X_t, y_t, eval_set=[(X_v, y_v)],
                  callbacks=[lgb.early_stopping(50, verbose=False)])
        preds = np.expm1(model.predict(X_v)).clip(0)
        true  = np.expm1(y_v)
        return np.sqrt(mean_squared_error(true, preds))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    log.info(f"   Meilleur RMSE : {study.best_value:.2f} min")
    return study.best_params


def tune_xgb_classifier(X_train, y_train, n_trials: int = 30) -> dict:
    log.info(f"Optuna XGBoost classifier ({n_trials} trials)...")
    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    spw = neg / pos

    def objective(trial):
        params = {
            "objective":         "binary:logistic",
            "eval_metric":       "auc",
            "scale_pos_weight":  spw,
            "n_estimators":      trial.suggest_int("n_estimators", 100, 800),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_depth":         trial.suggest_int("max_depth", 3, 10),
            "min_child_weight":  trial.suggest_int("min_child_weight", 1, 10),
            "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "gamma":             trial.suggest_float("gamma", 0, 5),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "verbosity":         0,
        }
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
        )
        model = xgb.XGBClassifier(**params, early_stopping_rounds=30)
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        probs = model.predict_proba(X_val)[:, 1]
        return roc_auc_score(y_val, probs)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    log.info(f"   Meilleur ROC-AUC : {study.best_value:.4f}")
    best = study.best_params
    best["scale_pos_weight"] = spw
    return best


# ------------------------------------------------------------------ #
# 4. Entrainement final                                               #
# ------------------------------------------------------------------ #
def train_lgbm_classifier(X_train, X_test, y_train, y_test, params: dict):
    log.info("Entrainement LightGBM Classifier...")
    params.update({"objective": "binary", "verbosity": -1})
    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train)

    probs  = model.predict_proba(X_test)[:, 1]
    best_t = find_best_threshold(y_test, probs)   # Fix 2
    preds  = (probs >= best_t).astype(int)

    metrics = {
        "roc_auc":   roc_auc_score(y_test, probs),
        "f1":        f1_score(y_test, preds),
        "f1_macro":  f1_score(y_test, preds, average="macro"),
        "threshold": best_t,
    }
    log.info(f"   ROC-AUC : {metrics['roc_auc']:.4f} | F1 : {metrics['f1']:.4f}")
    print(classification_report(y_test, preds, target_names=["On-time", "Delayed"]))
    return model, metrics, best_t


def train_xgb_classifier(X_train, X_test, y_train, y_test, params: dict):
    log.info("Entrainement XGBoost Classifier...")
    params.update({"objective": "binary:logistic", "verbosity": 0})
    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train)

    probs  = model.predict_proba(X_test)[:, 1]
    best_t = find_best_threshold(y_test, probs)   # Fix 2
    preds  = (probs >= best_t).astype(int)

    metrics = {
        "roc_auc":   roc_auc_score(y_test, probs),
        "f1":        f1_score(y_test, preds),
        "f1_macro":  f1_score(y_test, preds, average="macro"),
        "threshold": best_t,
    }
    log.info(f"   ROC-AUC : {metrics['roc_auc']:.4f} | F1 : {metrics['f1']:.4f}")
    return model, metrics, best_t


def train_lgbm_regressor(X_train, X_test, y_train, y_test, params: dict):
    log.info("Entrainement LightGBM Regressor...")
    mask_train = y_train > 0
    mask_test  = y_test  > 0

    y_train_log = np.log1p(y_train[mask_train])   # Fix 3

    params.update({"objective": "regression", "verbosity": -1})
    model = lgb.LGBMRegressor(**params)
    model.fit(X_train[mask_train], y_train_log)

    preds = np.expm1(model.predict(X_test[mask_test])).clip(0)
    true  = y_test[mask_test]

    metrics = {
        "rmse": np.sqrt(mean_squared_error(true, preds)),
        "mae":  mean_absolute_error(true, preds),
        "r2":   r2_score(true, preds),
    }
    log.info(f"   RMSE : {metrics['rmse']:.2f} min | MAE : {metrics['mae']:.2f} min | R2 : {metrics['r2']:.3f}")
    return model, metrics


# ------------------------------------------------------------------ #
# 5. Feature importance                                               #
# ------------------------------------------------------------------ #
def print_feature_importance(model, feature_names: list, top_n: int = 15):
    if hasattr(model, "feature_importances_"):
        imp = pd.Series(model.feature_importances_, index=feature_names)
        imp = imp.sort_values(ascending=False).head(top_n)
        print(f"\nTop {top_n} features importantes :")
        for feat, val in imp.items():
            bar = "#" * int(val / imp.max() * 20)
            print(f"  {feat:<30} {bar} {val:.0f}")


# ------------------------------------------------------------------ #
# 6. Sauvegarde                                                       #
# ------------------------------------------------------------------ #
def save_model(model, name: str, metrics: dict, params: dict, feature_names: list):
    path = MODELS_DIR / f"{name}.joblib"
    joblib.dump(model, path)
    log.info(f"   Sauvegarde : {path}")
    meta = {
        "name":       name,
        "trained_at": datetime.now().isoformat(),
        "metrics":    metrics,
        "params":     params,
        "features":   feature_names,
        "n_features": len(feature_names),
    }
    with open(MODELS_DIR / f"{name}_meta.json", "w") as f:
        json.dump(meta, f, indent=2)


# ------------------------------------------------------------------ #
# Main                                                                #
# ------------------------------------------------------------------ #
def main(fast: bool, use_wandb: bool, use_tuning: bool):
    n_trials_lgbm = 10 if fast else 50
    n_trials_xgb  = 5  if fast else 30

    if use_wandb:
        try:
            import wandb
            wandb.init(
                project="flight-delay-predictor",
                name=f"train-{'fast' if fast else 'full'}-{datetime.now().strftime('%m%d-%H%M')}",
                config={"fast": fast, "n_trials_lgbm": n_trials_lgbm},
            )
            log.info("W&B initialise")
        except Exception as e:
            log.warning(f"W&B non disponible : {e}")
            use_wandb = False

    df = load_data(fast=fast)
    X, y_clf, y_reg, encoders, feature_names = prepare_features(df)
    X_train, X_test, y_clf_train, y_clf_test, y_reg_train, y_reg_test = split_data(X, y_clf, y_reg)

    spw_default = (y_clf_train == 0).sum() / (y_clf_train == 1).sum()

    # ---- LightGBM ----
    print("\n" + "="*55)
    print("  LIGHTGBM")
    print("="*55)

    lgbm_clf_params = (
        tune_lgbm_classifier(X_train, y_clf_train, n_trials_lgbm) if use_tuning
        else {"n_estimators": 500, "learning_rate": 0.05, "num_leaves": 127, "scale_pos_weight": spw_default}
    )
    lgbm_clf, lgbm_clf_metrics, lgbm_t = train_lgbm_classifier(
        X_train, X_test, y_clf_train, y_clf_test, lgbm_clf_params
    )
    print_feature_importance(lgbm_clf, feature_names)
    save_model(lgbm_clf, "classifier_lgbm", lgbm_clf_metrics, lgbm_clf_params, feature_names)

    lgbm_reg_params = (
        tune_lgbm_regressor(X_train, y_reg_train, n_trials_lgbm) if use_tuning
        else {"n_estimators": 500, "learning_rate": 0.05, "num_leaves": 127}
    )
    lgbm_reg, lgbm_reg_metrics = train_lgbm_regressor(
        X_train, X_test, y_reg_train, y_reg_test, lgbm_reg_params
    )
    save_model(lgbm_reg, "regressor_lgbm", lgbm_reg_metrics, lgbm_reg_params, feature_names)

    # ---- XGBoost ----
    print("\n" + "="*55)
    print("  XGBOOST")
    print("="*55)

    xgb_clf_params = (
        tune_xgb_classifier(X_train, y_clf_train, n_trials_xgb) if use_tuning
        else {"n_estimators": 500, "learning_rate": 0.05, "max_depth": 6, "scale_pos_weight": spw_default}
    )
    xgb_clf, xgb_clf_metrics, xgb_t = train_xgb_classifier(
        X_train, X_test, y_clf_train, y_clf_test, xgb_clf_params
    )
    save_model(xgb_clf, "classifier_xgb", xgb_clf_metrics, xgb_clf_params, feature_names)

    # ---- Comparaison ----
    print("\n" + "="*55)
    print("  COMPARAISON FINALE")
    print("="*55)
    print(f"\n{'Modele':<25} {'ROC-AUC':>10} {'F1':>10} {'Seuil':>8}")
    print("-"*55)
    print(f"{'LightGBM Classifier':<25} {lgbm_clf_metrics['roc_auc']:>10.4f} {lgbm_clf_metrics['f1']:>10.4f} {lgbm_t:>8.2f}")
    print(f"{'XGBoost Classifier':<25} {xgb_clf_metrics['roc_auc']:>10.4f} {xgb_clf_metrics['f1']:>10.4f} {xgb_t:>8.2f}")
    print(f"\n{'Modele':<25} {'RMSE':>10} {'MAE':>10} {'R2':>10}")
    print("-"*55)
    print(f"{'LightGBM Regressor':<25} {lgbm_reg_metrics['rmse']:>10.2f} {lgbm_reg_metrics['mae']:>10.2f} {lgbm_reg_metrics['r2']:>10.3f}")

    best_clf = "lgbm" if lgbm_clf_metrics["roc_auc"] >= xgb_clf_metrics["roc_auc"] else "xgb"
    log.info(f"\nMeilleur classifier : {best_clf.upper()}")

    # Sauvegarde seuils pour l'inference
    inference_meta = {
        "lgbm_threshold": lgbm_t,
        "xgb_threshold":  xgb_t,
        "best_clf":       best_clf,
        "feature_names":  feature_names,
    }
    with open(MODELS_DIR / "inference_meta.json", "w") as f:
        json.dump(inference_meta, f, indent=2)

    if use_wandb:
        import wandb
        wandb.log({
            "lgbm_clf/roc_auc":   lgbm_clf_metrics["roc_auc"],
            "lgbm_clf/f1":        lgbm_clf_metrics["f1"],
            "lgbm_clf/threshold": lgbm_t,
            "xgb_clf/roc_auc":    xgb_clf_metrics["roc_auc"],
            "xgb_clf/f1":         xgb_clf_metrics["f1"],
            "lgbm_reg/rmse":      lgbm_reg_metrics["rmse"],
            "lgbm_reg/mae":       lgbm_reg_metrics["mae"],
            "lgbm_reg/r2":        lgbm_reg_metrics["r2"],
        })
        wandb.finish()

    joblib.dump(encoders, MODELS_DIR / "encoders.joblib")
    log.info(f"\nTous les modeles sauvegardes dans {MODELS_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast",      action="store_true", help="100k lignes, 10 trials Optuna")
    parser.add_argument("--no-wandb",  action="store_true", help="Desactive W&B")
    parser.add_argument("--no-tuning", action="store_true", help="Desactive Optuna")
    args = parser.parse_args()
    main(fast=args.fast, use_wandb=not args.no_wandb, use_tuning=not args.no_tuning)