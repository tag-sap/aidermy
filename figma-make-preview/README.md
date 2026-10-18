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

The static production output is written to `figma-make-preview/dist`.

## Production deployment — `https://aidermy.ru/ver2`

V2 is served as a **static build** under the path `/ver2/`, fully isolated from the
existing Next.js app (which continues to serve `/`). The build is configured with
`base: "/ver2/"` so all JS/CSS assets resolve to `/ver2/assets/...`.

Deployment (on the production VPS, in a dedicated directory — NOT inside `/var/www/aidermy`):

```bash
# One-time: clone the redesign branch into a separate directory
git clone --depth 1 --branch aidermy-redesign-preview https://github.com/tag-sap/aidermy.git /var/www/aidermy-ver2

# Build + deploy
cd /var/www/aidermy-ver2
./deploy-ver2.sh
```

nginx serves the built `dist/` with a dedicated `location /ver2/` block (see `deploy-ver2.sh`
and the accompanying nginx snippet). The main site `/` is untouched.

