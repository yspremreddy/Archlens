# ArchLens Frontend

React + TypeScript + Vite single-page app for ArchLens. See the
[repository root README](../README.md) for setup, environment variables, the
full feature tour, and screenshots.

## Local development

```bash
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev             # http://localhost:5173
```

Requires the ArchLens backend running separately (see the root README's
[Quick Start](../README.md#quick-start)).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check (`tsc -b`) and build for production |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run oxlint |
| `npm run test` | Run Vitest unit/component tests |
| `npm run test:e2e` | Run Playwright end-to-end tests (`e2e/`) |

`scripts/capture-screenshots.mjs` is a one-off utility used to regenerate the
screenshots in `../assets/screenshots/` against a running dev server +
backend — not part of the app itself.

## Structure

```
src/views/         one component per page section (Overview, Upload, …)
src/components/     shared evidence card, graph SVG rendering + pan/zoom
src/api/             typed fetch client mirroring the backend's Pydantic schemas
src/storage/         Web Storage (preferences) + IndexedDB (local result cache)
src/hooks/            shared async-action state (loading/error/cancel)
public/sw.js         hand-rolled service worker (static-asset caching only)
e2e/                  Playwright specs
```
