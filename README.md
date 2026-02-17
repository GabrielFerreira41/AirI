# ✈️ Flight Delay Prediction & Operations Analytics

## Contexte
Les retards aériens ont un impact direct sur les passagers (correspondances manquées, coûts, stress), sur les compagnies (réaffectation d’équipage, indemnités, image), et sur les aéroports (congestion, effet cascade).  
Ce projet vise à construire un pipeline data complet capable de **prédire les retards** et de **fournir une analyse explicable** des facteurs associés (horaire, aéroport, compagnie, route, congestion, météo en option).

## Idée
Créer un système **end-to-end** :
1) ingestion de données de vols à grande échelle  
2) nettoyage + feature engineering (dont variables temporelles et “congestion proxy”)  
3) entraînement d’un modèle de classification pour prédire si un vol arrivera avec **≥ 15 minutes** de retard  
4) dashboard interactif pour explorer :
   - retards par aéroport / compagnie / route  
   - causes et patterns temporels  
   - carte interactive des routes  
   - explications locales (ex: pourquoi ce vol est prédit en retard ?)

## Objectifs
### Objectif ML
- **Prédire** si un vol sera en retard (arrivée ≥ 15 min)  
- Fournir une **probabilité de retard** et une **interprétation** des facteurs

### Objectif analytics
- **Comprendre** les retards : où, quand, pourquoi  
- Mettre en évidence les routes/aéroports “hotspots”  
- Identifier les effets de congestion et d’accumulation de retards (effet cascade)

### Objectif produit / portfolio
- Un repo propre (pipeline reproductible, scripts, config)
- Un dashboard utilisable (Streamlit) + carte interactive
- Un rapport synthétique (résultats + limites + pistes d’amélioration)

---

## Données
### Source principale
**BTS / Airline On-Time Performance (US DOT)**  
Données historiques détaillées : horaires planifiés, horaires réels, retards, annulations, aéroports, compagnie, routes, etc.

> Justification : dataset standard, volumineux, structuré, idéal pour un projet “production-like”.

### Optionnel (V2)
**Météo horaire** (ex: Meteostat ou NOAA) pour enrichir la prédiction.

---

## Définition du problème
### Variable cible
- `is_late = 1` si **retard à l’arrivée ≥ 15 minutes**
- `is_late = 0` sinon

### Particularités importantes
- Les retards sont fortement **temporels** : il faut éviter toute fuite de données.
- Les patterns changent selon les périodes (saisons, événements, opérations).

---

## Approche (méthode)
### 1) Ingestion & stockage
- Téléchargement des fichiers (par mois/année)
- Stockage brut (`data/raw/`)
- Transformation vers format optimisé (`parquet`) dans `data/processed/`

### 2) Nettoyage
- Harmonisation des types (dates/heures)
- Gestion des valeurs manquantes
- Filtrage (ex: suppression des vols annulés si non traités)
- Construction robuste de la cible (retard ≥ 15 min)

### 3) Feature engineering
#### A. Variables temporelles
- heure de départ prévue, jour de la semaine, mois, saison
- “période de la journée” (matin/après-midi/soir)

#### B. Variables réseau / route
- aéroport origine/destination, compagnie, distance, route (Origin–Dest)

#### C. Congestion (proxy)
- nombre de vols partant du même aéroport sur une fenêtre proche (ex: ±1h)
- nombre de vols arrivant au même aéroport sur une fenêtre proche

#### D. Historique glissant (très important)
- taux de retard rolling (7j / 30j) par :
  - aéroport origine
  - compagnie
  - route
  - (optionnel) aéroport × heure

> Toutes les features historiques sont calculées **uniquement avec le passé** pour éviter la fuite.

### 4) Modélisation
- Baseline : Logistic Regression
- Modèle principal : **LightGBM ou CatBoost** (tabular performant)
- Gestion du déséquilibre : pondération de classes / seuil optimisé

### 5) Évaluation
- Split **temporel** (train < val < test)
- Métriques :
  - PR-AUC (utile si classe “retard” minoritaire)
  - ROC-AUC
  - calibration des probabilités
- Analyse d’erreurs :
  - par aéroport, compagnie, route, heure

### 6) Explicabilité
- SHAP global : facteurs majeurs
- SHAP local : explication d’un vol donné (pour le dashboard)

---

## Dashboard (Streamlit)
Le dashboard permet de :
1) **Explorer** les retards (analytics)
   - retards par aéroport / compagnie / route
   - heatmap heure × jour
   - top routes les plus problématiques
2) **Visualiser une carte** interactive des routes
   - lignes Origin→Dest
   - couleur/intensité = taux de retard ou volume de vols
3) **Faire une prédiction** sur un vol
   - probabilité de retard
   - top raisons (explication SHAP)

---

## Structure du projet
```text
flight-delay-prediction/
├─ data/
│  ├─ raw/
│  └─ processed/
├─ src/
│  ├─ ingest.py
│  ├─ clean.py
│  ├─ features.py
│  ├─ train.py
│  ├─ evaluate.py
│  └─ predict.py
├─ app/
│  ├─ Home.py
│  ├─ pages/
│  │  ├─ Analytics.py
│  │  ├─ Route_Map.py
│  │  └─ Prediction.py
├─ notebooks/
│  └─ EDA.ipynb
├─ configs/
│  └─ config.yaml
├─ tests/
├─ README.md
└─ requirements.txt
