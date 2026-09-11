#!/usr/bin/env bash

# ==============================================================================
# HELIOS — AI Surveillance & Threat Intelligence Operational Platform
# Unified Startup Orchestrator (start_helios.sh)
# ==============================================================================

set -e

# --- Script & Directory Resolution ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Styling & Colors ---
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    COLOR_RESET="\033[0m"
    COLOR_BOLD="\033[1m"
    COLOR_DIM="\033[2m"
    COLOR_CYAN="\033[36m"
    COLOR_GREEN="\033[32m"
    COLOR_YELLOW="\033[33m"
    COLOR_RED="\033[31m"
    COLOR_MAGENTA="\033[35m"
    COLOR_BLUE="\033[34m"
else
    COLOR_RESET=""
    COLOR_BOLD=""
    COLOR_DIM=""
    COLOR_CYAN=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_RED=""
    COLOR_MAGENTA=""
    COLOR_BLUE=""
fi

# --- Default Configurations ---
BACKEND_HOST="127.0.0.1"
BACKEND_PORT=8000
FRONTEND_PORT=5173
RUN_BACKEND=true
RUN_FRONTEND=true
AUTO_RELOAD=true
KILL_EXISTING=false
INIT_DB=false
AUTO_OPEN=false
QUIET=false

# --- Logging Helpers ---
log_info() {
    echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET} $*"
}

log_success() {
    echo -e "${COLOR_GREEN}[SUCCESS]${COLOR_RESET} $*"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $*" >&2
}

log_step() {
    echo -e "${COLOR_BOLD}${COLOR_MAGENTA}==>${COLOR_RESET} ${COLOR_BOLD}$*${COLOR_RESET}"
}

print_banner() {
    echo -e "${COLOR_CYAN}${COLOR_BOLD}"
    cat << "EOF"
  _    _ ______ _      _____ ____   _____ 
 | |  | |  ____| |    |_   _/ __ \ / ____|
 | |__| | |__  | |      | || |  | | (___  
 |  __  |  __| | |      | || |  | |\___ \ 
 | |  | | |____| |____ _| || |__| |____) |
 |_|  |_|______|______|_____\____/|_____/ 
EOF
    echo -e "${COLOR_RESET}${COLOR_DIM}  AI Surveillance & Threat Intelligence Operational Platform${COLOR_RESET}\n"
}

show_help() {
    print_banner
    cat << EOF
Usage: ./start_helios.sh [OPTIONS]

Starts the HELIOS platform (FastAPI Backend + React Vite Dashboard).

Options:
  -b, --backend-only       Start only the FastAPI backend server
  -f, --frontend-only      Start only the React Vite dashboard
  -p, --port-backend PORT  Port for backend server (default: 8000)
      --port-frontend PORT Port for frontend dashboard (default: 5173)
  -h, --host HOST          Host to bind backend (default: 127.0.0.1)
  -k, --kill               Automatically terminate processes holding configured ports
  -d, --init-db            Force initialize & seed the SQLite database before start
      --no-reload          Disable Uvicorn auto-reload (for production-like runs)
  -o, --open               Automatically open dashboard in default browser when ready
  -q, --quiet              Suppress banner and verbose log lines
      --help               Display this help message and exit

Examples:
  ./start_helios.sh                     # Start both backend & frontend
  ./start_helios.sh -k                  # Kill port blockers and start
  ./start_helios.sh --backend-only      # Run only the backend API
  ./start_helios.sh -o                  # Start and open browser
EOF
}

# --- CLI Options Parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--backend-only)
            RUN_BACKEND=true
            RUN_FRONTEND=false
            shift
            ;;
        -f|--frontend-only)
            RUN_BACKEND=false
            RUN_FRONTEND=true
            shift
            ;;
        -p|--port|--port-backend)
            BACKEND_PORT="$2"
            shift 2
            ;;
        --port-frontend)
            FRONTEND_PORT="$2"
            shift 2
            ;;
        --host)
            BACKEND_HOST="$2"
            shift 2
            ;;
        -k|--kill)
            KILL_EXISTING=true
            shift
            ;;
        -d|--init-db)
            INIT_DB=true
            shift
            ;;
        --no-reload)
            AUTO_RELOAD=false
            shift
            ;;
        -o|--open)
            AUTO_OPEN=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use './start_helios.sh --help' for available options."
            exit 1
            ;;
    esac
done

if [[ "$QUIET" = false ]]; then
    print_banner
fi

# --- Ensure Runtime Directories ---
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/data/evidence"
mkdir -p "$SCRIPT_DIR/storage/evidence"
mkdir -p "$SCRIPT_DIR/models/detection"

# --- Virtual Environment & Python Discovery ---
find_python_interpreter() {
    # Check active virtual environment
    if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
        echo "$VIRTUAL_ENV/bin/python"
        return 0
    fi
    # Check local .venv
    if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
        echo "$SCRIPT_DIR/.venv/bin/python"
        return 0
    fi
    # Check local .venv-1
    if [[ -x "$SCRIPT_DIR/.venv-1/bin/python" ]]; then
        echo "$SCRIPT_DIR/.venv-1/bin/python"
        return 0
    fi
    # Check global python3
    if command -v python3 >/dev/null 2>&1; then
        echo "$(command -v python3)"
        return 0
    fi
    return 1
}

PYTHON_BIN="$(find_python_interpreter || true)"

if [[ -z "$PYTHON_BIN" ]]; then
    log_error "Python interpreter could not be found. Please install Python 3.10+ or set up .venv."
    exit 1
fi

# --- Verify Backend Prerequisites ---
if [[ "$RUN_BACKEND" = true ]]; then
    log_step "Checking Python environment..."
    PY_VER="$("$PYTHON_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
    log_info "Using Python $PY_VER at: $PYTHON_BIN"

    if ! "$PYTHON_BIN" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
        log_error "'uvicorn' or 'fastapi' is missing from $PYTHON_BIN."
        log_error "Please install backend dependencies: $PYTHON_BIN -m pip install -r backend/requirements.txt"
        exit 1
    fi
    log_success "Backend dependencies verified."
fi

# --- Verify Node & Frontend Prerequisites ---
if [[ "$RUN_FRONTEND" = true ]]; then
    log_step "Checking Frontend environment..."
    if ! command -v node >/dev/null 2>&1; then
        log_error "Node.js is not installed or not in PATH. Please install Node.js 18+."
        exit 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
        log_error "npm is not installed or not in PATH."
        exit 1
    fi
    NODE_VER="$(node -v)"
    NPM_VER="$(npm -v)"
    log_info "Using Node $NODE_VER, npm $NPM_VER"

    if [[ ! -d "$SCRIPT_DIR/dashboard/node_modules" ]]; then
        log_warn "Dashboard dependencies missing. Running 'npm install' in dashboard..."
        npm install --prefix "$SCRIPT_DIR/dashboard"
        log_success "Frontend dependencies installed."
    else
        log_success "Frontend dependencies verified."
    fi
fi

# --- Configuration & Environment Check ---
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    if [[ -f "$SCRIPT_DIR/.env.example" ]]; then
        log_warn ".env file not found. Creating from .env.example..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        log_info "Created .env file. Update API keys and configuration as needed."
    else
        log_warn "Neither .env nor .env.example found. HELIOS will use default configurations."
    fi
fi

# --- Database Initialization / Seeding ---
DB_FILE="$SCRIPT_DIR/data/helios.db"
if [[ "$RUN_BACKEND" = true ]]; then
    if [[ ! -f "$DB_FILE" || "$INIT_DB" = true ]]; then
        log_step "Initializing HELIOS database & preloading cameras/zones..."
        "$PYTHON_BIN" "$SCRIPT_DIR/scripts/init_database.py"
        log_success "Database initialized successfully."
    else
        log_info "Database detected at $DB_FILE"
    fi
fi

# --- Port Management Helper ---
check_and_resolve_port() {
    local port="$1"
    local service_name="$2"

    local pids
    pids="$(lsof -ti :"$port" 2>/dev/null || true)"

    if [[ -n "$pids" ]]; then
        if [[ "$KILL_EXISTING" = true ]]; then
            log_warn "Port $port ($service_name) is in use by PID(s): $pids. Terminating..."
            for pid in $pids; do
                kill -9 "$pid" 2>/dev/null || true
            done
            sleep 1
            # Verify killed
            local check_again
            check_again="$(lsof -ti :"$port" 2>/dev/null || true)"
            if [[ -n "$check_again" ]]; then
                log_error "Failed to free port $port. Please kill process manually."
                exit 1
            fi
            log_success "Port $port freed."
        else
            log_error "Port $port ($service_name) is already in use by PID(s): $pids."
            log_error "Run with -k / --kill to terminate conflicting processes automatically,"
            log_error "or stop them manually: kill $pids"
            exit 1
        fi
    fi
}

if [[ "$RUN_BACKEND" = true ]]; then
    check_and_resolve_port "$BACKEND_PORT" "Backend API"
fi

if [[ "$RUN_FRONTEND" = true ]]; then
    check_and_resolve_port "$FRONTEND_PORT" "Frontend Dashboard"
fi

# --- Process Lifecycle Management ---
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    log_step "Shutting down HELIOS services..."

    if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        log_info "Stopping frontend dashboard (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        log_info "Stopping backend server (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi

    # Wait briefly for graceful shutdown
    sleep 1

    # Force kill if still lingering
    if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill -9 "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill -9 "$BACKEND_PID" 2>/dev/null || true
    fi

    log_success "HELIOS services stopped cleanly."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# --- Launch Backend ---
if [[ "$RUN_BACKEND" = true ]]; then
    log_step "Launching HELIOS Backend API on $BACKEND_HOST:$BACKEND_PORT..."

    BACKEND_CMD=(
        "$PYTHON_BIN" -m uvicorn main:app
        --app-dir backend
        --host "$BACKEND_HOST"
        --port "$BACKEND_PORT"
    )

    if [[ "$AUTO_RELOAD" = true ]]; then
        BACKEND_CMD+=(--reload --reload-dir backend --reload-dir config)
    fi

    "${BACKEND_CMD[@]}" > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
    BACKEND_PID=$!
    log_info "Backend process started (PID: $BACKEND_PID, Log: logs/backend.log)"

    # Wait for backend health check
    log_info "Waiting for Backend API readiness..."
    HEALTH_URL="http://$BACKEND_HOST:$BACKEND_PORT/api/v1/system/health"
    READY=false

    for i in {1..30}; do
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            log_error "Backend process exited prematurely. Check logs/backend.log:"
            echo -e "${COLOR_DIM}"
            tail -n 25 "$SCRIPT_DIR/logs/backend.log"
            echo -e "${COLOR_RESET}"
            exit 1
        fi

        if curl -s -f "$HEALTH_URL" >/dev/null 2>&1 || grep -q "Application startup complete" "$SCRIPT_DIR/logs/backend.log" 2>/dev/null; then
            READY=true
            break
        fi
        sleep 0.5
    done

    if [[ "$READY" = true ]]; then
        log_success "Backend API is ready and healthy!"
    else
        log_warn "Backend did not respond to health check within 15s, but process is still running."
    fi
fi

# --- Launch Frontend ---
if [[ "$RUN_FRONTEND" = true ]]; then
    log_step "Launching HELIOS Dashboard on port $FRONTEND_PORT..."

    (
        cd "$SCRIPT_DIR/dashboard"
        npm run dev -- --host "$BACKEND_HOST" --port "$FRONTEND_PORT"
    ) > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    log_info "Frontend process started (PID: $FRONTEND_PID, Log: logs/frontend.log)"

    # Give Vite a moment to bind
    sleep 1
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        log_error "Frontend process exited prematurely. Check logs/frontend.log:"
        echo -e "${COLOR_DIM}"
        tail -n 25 "$SCRIPT_DIR/logs/frontend.log"
        echo -e "${COLOR_RESET}"
        exit 1
    fi
    log_success "Frontend dashboard server running."
fi

# --- Service Status Summary ---
echo ""
echo -e "${COLOR_BOLD}${COLOR_GREEN}================================================================${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}               HELIOS PLATFORM OPERATIONAL                      ${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}================================================================${COLOR_RESET}"
if [[ "$RUN_FRONTEND" = true ]]; then
    echo -e "  ${COLOR_BOLD}Dashboard UI:${COLOR_RESET}     ${COLOR_CYAN}http://localhost:${FRONTEND_PORT}${COLOR_RESET}"
fi
if [[ "$RUN_BACKEND" = true ]]; then
    echo -e "  ${COLOR_BOLD}Backend API:${COLOR_RESET}      ${COLOR_CYAN}http://${BACKEND_HOST}:${BACKEND_PORT}${COLOR_RESET}"
    echo -e "  ${COLOR_BOLD}API Docs:${COLOR_RESET}         ${COLOR_CYAN}http://${BACKEND_HOST}:${BACKEND_PORT}/docs${COLOR_RESET}"
    echo -e "  ${COLOR_BOLD}WebSocket:${COLOR_RESET}        ${COLOR_CYAN}ws://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/ws${COLOR_RESET}"
    echo -e "  ${COLOR_BOLD}Health Status:${COLOR_RESET}    ${COLOR_CYAN}http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/system/health${COLOR_RESET}"
fi
echo -e "  ${COLOR_BOLD}Log Files:${COLOR_RESET}        ${COLOR_DIM}logs/backend.log, logs/frontend.log${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}================================================================${COLOR_RESET}"
echo -e "${COLOR_DIM}Press [Ctrl+C] to gracefully stop all HELIOS services.${COLOR_RESET}\n"

# --- Optional Auto-Open Browser ---
if [[ "$AUTO_OPEN" = true && "$RUN_FRONTEND" = true ]]; then
    DASHBOARD_URL="http://localhost:${FRONTEND_PORT}"
    log_info "Opening $DASHBOARD_URL in default browser..."
    if command -v open >/dev/null 2>&1; then
        open "$DASHBOARD_URL"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$DASHBOARD_URL"
    fi
fi

# --- Stream Logs / Wait for Interrupt ---
# Keep parent script running and monitoring child processes
while true; do
    if [[ "$RUN_BACKEND" = true ]] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        log_error "Backend service terminated unexpectedly."
        break
    fi
    if [[ "$RUN_FRONTEND" = true ]] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        log_error "Frontend service terminated unexpectedly."
        break
    fi
    sleep 2
done

cleanup
