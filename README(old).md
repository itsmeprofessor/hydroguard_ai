# HydroGuard-AI 🌧️

**Weather Anomaly Detection for Flash Flood & Cloudburst Early Warning in Pakistan**

FastAPI backend (TensorFlow Autoencoder + LSTM Hybrid) + Flutter cross-platform frontend.

---

## Project Structure

```
hydroguard_ai/
├── backend/                        # Python FastAPI backend
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py             # Shared dependencies (auth)
│   │   │   └── routes/
│   │   │       ├── system.py       # GET / /health /model/info
│   │   │       ├── training.py     # POST /train
│   │   │       ├── prediction.py   # POST /predict /predict/batch
│   │   │       ├── anomalies.py    # GET  /anomalies /anomalies/{id}
│   │   │       └── risk_analytics.py # GET /risk-map /analytics
│   │   ├── core/
│   │   │   └── config.py           # All config (env-driven)
│   │   ├── db/
│   │   │   └── database.py         # ORM models + repositories
│   │   ├── schemas/
│   │   │   └── __init__.py         # Pydantic request/response models
│   │   ├── services/
│   │   │   └── anomaly_service.py  # ML inference service (singleton)
│   │   └── main.py                 # App factory + lifespan
│   ├── ml/
│   │   └── models/
│   │       └── autoencoder.py      # WeatherAutoencoder, LSTMAutoencoder, HybridDetector
│   ├── utils/
│   │   ├── preprocessing.py        # WeatherDataPreprocessor
│   │   ├── city_keys.py            # City name slug/matching utilities
│   │   └── visualization.py        # Training analysis plots
│   ├── data/                       # Training CSVs (gitignored except .gitkeep)
│   ├── saved_models/               # Persisted .keras + .joblib artifacts
│   ├── logs/                       # Rotating log files
│   ├── requirements.txt
│   └── run_server.py               # CLI server launcher
├── frontend/                       # Flutter app (weather_anomaly_app/)
├── scripts/
│   ├── train.py                    # Offline training CLI
│   ├── evaluate.py                 # Model evaluation + CSV export
│   └── tune_threshold.py           # Adjust anomaly threshold post-training
├── tests/
│   └── test_api.py                 # Pytest API test suite
├── .env.example                    # Environment variable template
├── .gitignore
├── Dockerfile                      # Multi-stage production image
├── docker-compose.yml
└── pyproject.toml                  # pytest config
```

---

## Quickstart

### 1. Setup

```bash
cd hydroguard_ai
cp .env.example .env          # fill in ADMIN_TOKEN, DATABASE_URL etc.
pip install -r backend/requirements.txt
```

### 2. Train the model

```bash
python scripts/train.py --data backend/data/pakistan_weather_2000_2024.csv --use-lstm
```

### 3. Run the API server

```bash
cd backend
python run_server.py --reload   # dev
python run_server.py            # production
```

API Swagger: http://127.0.0.1:8000/docs

### 4. Docker

```bash
docker compose up --build
```

---

## Key API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | System health + model status |
| GET | `/model/info` | — | Model architecture + training metadata |
| POST | `/train` | Admin | Train / retrain model |
| POST | `/predict` | — | Single observation inference |
| POST | `/predict/batch` | — | Batch inference (single DB session) |
| GET | `/anomalies` | — | Paginated anomaly records |
| GET | `/anomalies/statistics` | — | Anomaly stats over dataset |
| GET | `/risk-map` | — | HRI scores for all Pakistan cities |
| GET | `/analytics` | Admin | Weekly analytics dashboard data |

**Admin endpoints** require `X-Admin-Token: <value>` header.

---

## ML Architecture

```
Input → WeatherDataPreprocessor
         (impute → weighted-scale → one-hot encode)
       ↓
Autoencoder (reconstruction error → anomaly score)
       +
LSTM Autoencoder (7-day sequences per city → temporal score)
       ↓
HybridAnomalyDetector (combined weighted score)
       ↓
HRI Composite (0-100): 40% anomaly + 35% rainfall + 25% regional vulnerability
       +
Cloudburst Rule Engine (physics-based risk category)
```

**Flood-focus feature weights** are applied before StandardScaling:
- `prcp` × 3.0, `humidity` × 2.0, `pressure` × 2.0, `cloud_cover` × 1.5
- Temperature features × 0.1 (intentionally de-weighted)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_TOKEN` | `changeme-set-in-env` | Required for `/train` and `/analytics` |
| `DATABASE_URL` | SQLite | Switch to PostgreSQL for production |
| `CORS_ORIGINS` | `*` | Restrict to your frontend domain in prod |
| `HYBRID_WARMUP` | `true` | Seed LSTM buffers on startup |
| `MODEL_EPOCHS` | `100` | Override training epochs |
| `THRESHOLD_K` | `2.5` | Anomaly threshold multiplier |

---

## Scripts

```bash
# Train
python scripts/train.py --data backend/data/... [--use-lstm] [--epochs 200]

# Evaluate (generates evaluation_results/detected_anomalies.csv + report.json)
python scripts/evaluate.py

# Tune threshold without retraining
python scripts/tune_threshold.py --k 3.0

# Run tests
pytest tests/ -v
```

---

## Docker & CI/CD

- **Multi-stage Dockerfile**: deps layer cached separately → fast rebuilds
- **Non-root runtime user** (`hydroguard`)
- **HEALTHCHECK** via `curl /health`
- **GitHub Actions** (`.github/workflows/ci.yml`):
  - Lint (Ruff), type-check (mypy), pytest, Docker build + smoke test
  - Deployment hooks (Docker Hub / SSH VPS) — uncomment to enable

---

## Development

```bash
# Type check
mypy backend/app/core/config.py backend/app/schemas/__init__.py --ignore-missing-imports

# Lint
ruff check backend/ --select E,W,F,I

# Format
ruff format backend/
```
