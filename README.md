# Smart Home Energy Monitoring and Management System (SHEMMS)

## Project Overview
SHEMMS is a software platform that connects to smart plugs installed between home appliances and wall outlets to collect real-time electrical power data. It delivers monitoring, analytics, and control features to users.

## System Architecture

| Component | Stack | Role |
|---|---|---|
| `frontend/` | Next.js | Web dashboard — live readings, appliances, schedules, analytics |
| `backend/` | Node.js / Express | REST API, MQTT ingest, Socket.IO, alerting, hourly ETL |
| `analytics/` | Python / Flask | Per-device anomaly detection, forecasting, homomorphic-encryption layer |
| `simulator/` | Python | Publishes synthetic smart-plug readings over MQTT |
| `firmware/` | ESP32 / Arduino | Node firmware and a standalone relay-command sender |

Data stores: PostgreSQL (users, appliances, spaces, schedules, alerts), InfluxDB (encrypted time-series readings), MongoDB (hourly aggregates and trained models).

## Local Development Setup
1. Clone the repository.
2. Copy the `.env.example` file to `.env` in each service folder (`backend`, `frontend`, `analytics`, `simulator`) and fill in the values marked `CHANGE_ME`.
3. Run `docker compose up --build` to start the full stack.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:3001 |
| Analytics API | http://localhost:5000 |
| pgAdmin | http://localhost:5050 |
| mongo-express | http://localhost:8081 |

## Firmware
Open `firmware/shemms_node/` in the Arduino IDE. Copy `secrets.example.h` to `secrets.h` and fill in your WiFi credentials, MQTT broker details, and a 32-byte AES key. The key must match `MQTT_AES_KEY` in `backend/.env`.

## Analytics Utilities
Run inside the analytics container (`docker compose exec analytics ...`):

- `python src/scripts/seed_synthetic.py` — generate a test dataset so models reach READY immediately
- `python src/scripts/train.py` — report readiness and train qualifying devices
- `python src/scripts/evaluate.py` — score the detector against ground-truth labels
- `python src/scripts/reset_db.py` — clear alerts, checkpoints, and trained models

## API Reference
Import `postman/shemms_postman_collection.json` and `postman/shemms_local_env.json` into Postman. Architecture notes are in `docs/`.
