# Frontend development guide

The frontend is the React 19 and TypeScript user interface for the E-Invoicing API Publisher. It provides authentication, the API dashboard, submission and version workflows, schema mapping, and connection validation.

## Prerequisites

- Node.js 22, matching `frontend/Dockerfile`
- npm with lockfile support
- A running backend at <http://127.0.0.1:8000> for local development

## Install and run

From `frontend/`:

```bash
npm ci
npm run dev
```

Vite normally serves the application at <http://localhost:5173>. The FastAPI CORS configuration permits `localhost:5173` and `127.0.0.1:5173` during local development.

The shared Axios client uses `VITE_API_BASE_URL` when it is defined and otherwise calls <http://127.0.0.1:8000>. The Docker build sets `VITE_API_BASE_URL=/`, allowing Nginx to proxy `/api/` requests to the backend container.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite development server |
| `npm run lint` | Run ESLint across the frontend |
| `npm run build` | Type-check and create the production bundle in `dist/` |
| `npm run preview` | Serve the production bundle locally for inspection |

## Structure

```text
frontend/
├── public/              static assets
├── src/
│   ├── components/      shared forms and page layout
│   ├── pages/           login, registration, dashboard, API detail, and mapping views
│   ├── services/        typed backend API calls
│   ├── store/           Redux Toolkit state
│   ├── styles/          shared theme styles
│   ├── types/           shared TypeScript models
│   ├── utils/           Axios client, authentication session, and helpers
│   ├── App.tsx          routes and route guards
│   └── main.tsx         React entry point
├── nginx.conf           production SPA and `/api/` proxy configuration
├── Dockerfile           Node build and Nginx runtime image
└── package.json
```

## Authentication behaviour

- Successful login or registration stores the JWT and user summary in browser local storage.
- The Axios request interceptor attaches the JWT as a Bearer token.
- An authenticated request receiving HTTP 401 clears the stored session and redirects to `/login`.
- Routes under `/homepage`, `/apis/:id`, and `/schema-mapping` require a stored token; the backend remains responsible for actual authorization.

## API reference

Frontend service modules under `src/services/` are the client-side integration boundary. The running backend's generated OpenAPI document and Swagger UI are the canonical API references:

- <http://127.0.0.1:8000/openapi.json>
- <http://127.0.0.1:8000/docs>

Do not maintain a separate hand-written endpoint contract when the generated OpenAPI schema is available.
