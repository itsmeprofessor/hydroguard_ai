Here is a clean, production-ready `README.md` for your **HydroGuard-AI v3.1** project. I’ve structured it like a real open-source + industry-grade ML system so it’s suitable for GitHub, portfolio, and deployment documentation.

---

```markdown
# 🌊 HydroGuard-AI v3.1

**Production-grade Flood & Weather Anomaly Detection System for Pakistan**

HydroGuard-AI is a full-stack AI system designed to predict weather anomalies, flood risks, and cloudburst events across 10 major cities in Pakistan using hybrid deep learning models and real-time APIs.

It combines:
- 🤖 Machine Learning (Autoencoder + LSTM + Bahdanau Attention)
- ⚡ FastAPI backend with WebSocket streaming
- 🌐 Web-first citizen application
- 🧠 Admin intelligence dashboard
- 🐳 Dockerized production deployment

---

## 📌 Supported Cities

- Islamabad
- Lahore
- Karachi
- Peshawar
- Quetta
- Gilgit

---

## 🧠 Core Architecture

### 🔙 Backend (FastAPI)
Located in `backend/`

Features:
- City-specific hybrid ML models (Autoencoder + LSTM + Attention)
- JWT authentication (access + refresh rotation)
- Role-based access control (USER / ANALYST / ADMIN)
- WebSocket real-time anomaly & risk broadcasting
- SQLAlchemy ORM with PostgreSQL / SQLite support
- Rate limiting (SlowAPI)
- Heuristic fallback system for untrained cities

---

### 🤖 ML System

Each city has its own trained model:

#### 🧩 Hybrid Model Architecture
- Autoencoder (feature reconstruction anomaly detection)
- LSTM (7-step temporal forecasting)
- Bahdanau Attention (sequence focus weighting)

#### ⚙️ Final Prediction Formula
```

Hybrid Score = 0.55 × AE Score + 0.45 × LSTM Score

````

#### 📊 Output Structure
```json
{
  "risk_level": "Low | Medium | High",
  "anomaly_score": 0.78,
  "confidence": 0.91,
  "is_anomaly": true,
  "ae_score": 0.72,
  "lstm_score": 0.81,
  "hri_score": 64
}
````

---

### 🌐 Public Citizen Web App

Location: `frontend/citizen_app/`

A lightweight, mobile-first web app:

* 5 screens:

  * Home
  * Forecast
  * Alerts
  * Learn
  * Settings
* Live risk visualization
* 5-minute polling system (no WebSockets)
* Multi-language support:

  * English
  * Urdu
  * Punjabi
  * Pashto
  * Sindhi
  * Balochi
* Dark / Light mode
* Fully based on provided UI design ZIP

---

### 🧑‍💼 Admin Dashboard

Location: `frontend/web_dashboard/admin_dashboard/`

Features:

* JWT-secured admin panel
* Real-time WebSocket monitoring
* Pakistan risk heatmap (SVG-based)
* Model training controls per city
* Analytics & anomaly tracking
* User & system management tools

---

## ⚙️ Backend Features

### 🔐 Authentication System

* JWT Access Token (30 min)
* Refresh Token Rotation (7 days)
* Secure password hashing (bcrypt)
* Role-based access control

### 📡 API Endpoints

#### Core

* `GET /health`
* `GET /model/info`
* `GET /risk-map`

#### Authentication

* `POST /auth/register`
* `POST /auth/login`
* `POST /auth/refresh`
* `GET /auth/me`

#### Predictions

* `POST /predict`
* `POST /predict/batch`

#### Cities

* `GET /cities`
* `GET /cities/{city}/risk`
* `GET /cities/{city}/forecast`
* `POST /cities/{city}/predict`
* `POST /cities/{city}/train`

#### Analytics

* `GET /anomalies`
* `GET /analytics`
* `GET /admin/analytics`

#### WebSockets

* `/ws/anomalies`
* `/ws/risk-map`
* `/ws/health`

---

## 🧪 Machine Learning Pipeline

### 📊 Features Used

* Precipitation (PRCP)
* Humidity
* Pressure
* Cloud Cover
* Temperature (TAVG, TMAX, TMIN)
* Wind Speed
* Dew Point

### ⚙️ Preprocessing

* Median Imputation
* Standard Scaling
* MinMax Scaling (temporal features)
* One-hot encoding (categorical)

### 🌧️ Cloudburst Detection Engine

Weighted heuristic:

```
0.45 × precipitation
+ 0.25 × pressure
+ 0.20 × humidity
+ 0.10 × cloud cover
```

---

## 🏗️ System Design

### Backend Flow

```
Request → Router → Auth → Service Layer → ML Model → Repository → DB → WebSocket Broadcast
```

### Model Flow

```
Weather Data → Preprocessor → AE + LSTM → Attention → Hybrid Score → Risk Engine → HRI Output
```

---

## 🐳 Docker Deployment

### Full Stack

```bash
docker compose up --build
```

Includes:

* FastAPI Backend
* PostgreSQL 16
* Redis 7
* Nginx Reverse Proxy

---

## 🚀 Run Locally

### Backend

```bash
pip install -r backend/requirements.txt
python backend/run_server.py --reload
```

### Citizen App

```bash
cd frontend/citizen_app
python -m http.server 5500
```

### Admin Dashboard

```bash
cd frontend/web_dashboard/admin_dashboard
python -m http.server 5501
```

---

## 🧠 Model Training

### Train All Cities

```bash
python scripts/train_city.py --all --epochs 150
```

### Train Single City

```bash
python scripts/train_city.py --city Islamabad --epochs 200
```

### AE Only Mode

```bash
python scripts/train_city.py --city Karachi --no-lstm
```

---

## 📦 Project Structure

```
backend/
 ├── app/
 │   ├── api/
 │   ├── core/
 │   ├── ml/
 │   ├── services/
 │   ├── db/
 │   ├── auth/
 │   └── realtime/
 ├── saved_models/
 ├── run_server.py

frontend/
 ├── citizen_app/
 └── web_dashboard/

scripts/
tests/
docker-compose.yml
nginx/
```

---

## 🔐 Key Design Constraints

* ❌ No BiLSTM (causal forecasting only)
* ❌ No global ML model (city-specific only)
* ❌ WebSocket only for admin + backend (citizen app uses polling)
* ❌ Strict adherence to provided UI design ZIP
* ⚠️ SQLite not safe for multi-worker production
* ⚠️ JWT secret must be configured in production

---

## 📈 System Highlights

* 🔥 Real-time anomaly detection
* 🌧️ Flood & cloudburst prediction engine
* 🧠 Hybrid deep learning architecture
* 🏙️ City-specific intelligence models
* 📡 Live WebSocket alert system
* 🌐 Full web-first redesign (v3.1)
* 🐳 Production-ready Docker setup

---

## 👨‍💻 Developer Notes

* Backend is fully modular and service-oriented
* ML models are hot-swappable per city
* Web dashboards use CDN-based React (no build step)
* Citizen app is lightweight and offline-tolerant
* Designed for scalability + real-world deployment

---

## 📜 License

This project is for academic and professional demonstration purposes.

---

## 🚀 Author

**Zain Mohyuddin**
HydroGuard AI System Architect & ML Developer


