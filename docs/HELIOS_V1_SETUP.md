# HELIOS V1 SETUP & INSTALLATION GUIDE

## Installation, Environment Configuration & First-Time Setup

**Project:** HELIOS  
**Document:** Prerequisites, Dependency Setup, Database Seeding & Startup Verification  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. System Prerequisites

Before installing HELIOS, ensure your host environment meets the following requirements:
- **Operating System**: macOS (Apple Silicon / Intel), Ubuntu Linux 22.04+, or Debian 12.
- **Python**: Version 3.10 or higher (fully tested and compatible with Python 3.14).
- **Node.js**: Version 18.0 or higher & **npm** 9+.
- **Video Decoding Tools**: `ffmpeg` (recommended for test video streaming).
- **Hardware**: Minimum 4 CPU cores, 8 GB RAM (NVIDIA GPU or Apple Silicon MPS optional for accelerated inference).

---

# 2. Step-by-Step Installation

### Step 1: Clone or Navigate to Project Root
```bash
cd /Users/princepatel/Documents/Helios
```

### Step 2: Set Up Python Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
```

### Step 3: Install Frontend Dependencies
```bash
cd dashboard
npm install
cd ..
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env` if not already present:
```bash
cp .env.example .env
```
Open `.env` and set any optional API keys:
- `GEMINI_API_KEY`: For Google Gemini 1.5 cloud AI features.
- `OPENROUTER_API_KEY`: For OpenRouter Nemotron / Gemma reasoning models.
- `ROBOFLOW_API_KEY`: For hosted Roboflow drone/face detection.
- *(Note: HELIOS runs completely fine locally without API keys using fallback rules and local Ollama).*

### Step 5: Initialize the SQLite Database
Initialize all 20 SQLite tables, build indexes, and seed default cameras/zones:
```bash
.venv/bin/python scripts/init_database.py
```

---

# 3. Launching HELIOS

### Single-Command Startup (Recommended)
Launch both the FastAPI backend and the React Vite dashboard simultaneously with health checking and automatic port cleanup:
```bash
./start_helios.sh -k -o
```
- `-k`: Automatically terminates any conflicting processes on ports 8000 or 5173.
- `-o`: Automatically opens the dashboard in your default browser once healthy.

### Manual Individual Service Startup

#### Backend Server:
```bash
source .venv/bin/activate
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
API Documentation will be accessible at: `http://127.0.0.1:8000/docs`.

#### Frontend Dashboard:
```bash
cd dashboard
npm run dev
```
Dashboard will be accessible at: `http://localhost:5173`.

---

# 4. Verifying Installation

Run the automated diagnostic health check:
```bash
.venv/bin/python scripts/health_check.py
```

Or execute the complete unit and integration test suite:
```bash
.venv/bin/pytest backend/tests
```
