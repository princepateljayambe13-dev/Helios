# HELIOS V1 DEPLOYMENT & ORCHESTRATION SPECIFICATION

## System Specification: Deployment Architecture, Process Lifecycle & Orchestration

**Project:** HELIOS  
**Document:** Runtime Orchestration, Process Management, Ports & Deployment  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Executive Summary & Runtime Topology

HELIOS provides a unified orchestration architecture allowing single-command startup, clean process lifecycle management, automated port conflict resolution, and graceful shutdown:
- **Backend Service**: FastAPI application hosted on Uvicorn (Port 8000).
- **Frontend Service**: React 18 + Vite development server or static production bundle (Port 5173).
- **Database Engine**: Embedded SQLite database (`data/helios.db`) in WAL mode.
- **Orchestrator**: POSIX-compliant Bash orchestrator (`start_helios.sh`).

---

# 2. Unified Startup Orchestrator (`start_helios.sh`)

### 2.1 Command Usage & Flag Options
```bash
./start_helios.sh [OPTIONS]
```

| Flag | Long Option | Description |
| :--- | :--- | :--- |
| `-k` | `--kill` | Scans ports 8000 and 5173; forcefully terminates blocking PIDs (`lsof -ti :port \| xargs kill -9`). |
| `-o` | `--open` | Automatically opens `http://localhost:5173` in default system browser once services are healthy. |
| `-b` | `--backend-only`| Launches only the FastAPI backend server. |
| `-f` | `--frontend-only`| Launches only the Vite frontend dashboard. |
| `-d` | `--init-db` | Executes `scripts/init_database.py` to recreate/seed SQLite database before launch. |
| `-p` | `--port` | Overrides backend port (default: 8000). |
| | `--port-frontend` | Overrides frontend port (default: 5173). |
| | `--no-reload` | Disables Uvicorn auto-reload for production deployment. |
| `-q` | `--quiet` | Suppresses ASCII banner and verbose telemetry outputs. |

### 2.2 Startup Flow & Readiness Verification
1. **Directory Discovery**: Resolves script path; changes directory to project root.
2. **Environment Discovery**: Locates Python virtual environment (`.venv/bin/python` or active `VIRTUAL_ENV`).
3. **Dependency Verification**: Verifies `fastapi`, `uvicorn`, `node`, and `npm`.
4. **Configuration Check**: Clones `.env.example` to `.env` if missing.
5. **Port Conflict Management**: Frees configured ports if `-k` is set.
6. **Backend Launch**: Starts Uvicorn in background, redirecting stdout/stderr to `logs/backend.log`.
7. **Readiness Probe**: Polls `http://127.0.0.1:8000/api/v1/system/health` up to 30 attempts (15 seconds).
8. **Frontend Launch**: Starts Vite development server, piping logs to `logs/frontend.log`.
9. **Signal Trapping**: Intercepts `SIGINT` (Ctrl+C), `SIGTERM`, and `EXIT`, executing clean termination of both child process groups.

---

# 3. Production Deployment (Static Dashboard + Uvicorn)

For deployment in production environments:

### 3.1 Step 1: Build Production Dashboard
```bash
cd dashboard
npm install
npm run build
```
This generates optimized static HTML/CSS/JS artifacts in `dashboard/dist/`.

### 3.2 Step 2: Serve via Reverse Proxy (Nginx)
```nginx
server {
    listen 80;
    server_name helios.internal;

    # Frontend Static Files
    location / {
        root /opt/helios/dashboard/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend REST API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Real-Time WebSockets
    location /api/v1/ws {
        proxy_pass http://127.0.0.1:8000/api/v1/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_read_timeout 86400s;
    }
}
```

### 3.3 Step 3: Production Backend Daemon (Systemd)
```ini
[Unit]
Description=HELIOS Surveillance Platform Backend
After=network.target

[Service]
User=helios
WorkingDirectory=/opt/helios
ExecStart=/opt/helios/.venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
