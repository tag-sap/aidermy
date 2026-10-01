# Aidermy redesign preview

Standalone React + Vite prototype of the new Aidermy interface. It uses mock data and does not replace the existing Next.js application or Python backend.

## Local run

```bash
cd figma-make-preview
pnpm install
pnpm dev
```

## Production build

```bash
cd figma-make-preview
pnpm install --frozen-lockfile
pnpm build
```

The static production output is written to `figma-make-preview/dist`. For a separate Vercel production trial, set **Root Directory** to `figma-make-preview`, build command to `pnpm build`, and output directory to `dist`.
