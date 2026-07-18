# Enterprise RAG — Frontend

React + TypeScript + Tailwind chat UI for the Enterprise RAG backend.

## Develop

```bash
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies `/api/*` to the
backend at `http://127.0.0.1:8000` (see `vite.config.ts`). Override the
target with the `VITE_API_PROXY_TARGET` env var if the backend runs
elsewhere:

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8010 npm run dev
```

## Build

```bash
npm run build
```

Outputs to `dist/`. Serve it behind any static file server / reverse proxy
that forwards `/api/*` to the FastAPI backend.

## Structure

- `src/api/` — axios client (JWT bearer auth, 401 → redirect to `/login`) and typed endpoint wrappers
- `src/context/AuthContext.tsx` — signup/login/logout + current-user state
- `src/pages/` — `AuthPage` (login/signup), `ChatPage` (main app shell)
- `src/components/` — `Sidebar`, `ChatWindow`, `MessageBubble`, `UploadDialog`
