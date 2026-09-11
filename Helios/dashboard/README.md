# HELIOS Dashboard Frontend

The HELIOS Operational Surveillance Dashboard built with React, Vite, and WebSockets.

## Setup & Running

```bash
# Install dependencies
npm install

# Run dev server
npm run dev

# Build for production
npm run build
```

## Configured Endpoints
- **REST API**: `http://127.0.0.1:8000/api/v1`
- **WebSocket Stream**: `ws://127.0.0.1:8000/api/v1/ws`

Override API host by setting `localStorage.setItem('heliosApiBase', 'http://your-backend-ip:8000')`.
