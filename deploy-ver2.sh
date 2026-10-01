#!/bin/bash
set -euo pipefail

# Деплой V2 (figma-make-preview) как статический билд под путь /ver2/.
# НЕ трогает основной Next.js-сайт (/) и backend — это отдельная статика.

cd "$(dirname "$0")"

echo "📦 Pulling redesign branch..."
git pull origin aidermy-redesign-preview

echo "📦 Installing V2 dependencies..."
cd figma-make-preview
npm install --no-fund --no-audit

echo "🏗️  Building V2 (base=/ver2/)..."
npm run build

echo ""
echo "✅ V2 build ready: $(pwd)/dist"
echo "   nginx должен отдавать этот каталог по /ver2/ (см. nginx-ver2.conf)."
