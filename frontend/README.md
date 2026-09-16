# DocQuery Frontend

React SPA for DocQuery, built with [Vite](https://vitejs.dev).

## Available scripts

### `npm run dev`

Starts the Vite dev server in development mode.
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.
Hot module reload picks up changes instantly.

### `npm test`

Runs the test suite once with [Vitest](https://vitest.dev) + React Testing Library.

### `npm run build`

Builds the app for production to the `dist` folder.

### `npm run preview`

Serves the production build from `dist` locally, for a final check before deploying.

## Environment variables

| Variable        | Default                 | Notes                                   |
|-----------------|--------------------------|------------------------------------------|
| `VITE_API_URL`  | `http://localhost:8000` | Base URL of the DocQuery backend API     |

Set via Vite's `import.meta.env`, not `process.env` — see [Vite env docs](https://vitejs.dev/guide/env-and-mode.html).

