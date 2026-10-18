#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "📦 Pulling latest changes from GitHub..."
git pull origin main

echo "📦 Installing frontend dependencies (Vite)..."
cd figma-make-preview
npm install --no-fund --no-audit

echo "🏗️ Building frontend (Vite)..."
npm run build
cd ..

echo "🐍 Updating backend dependencies..."
cd backend
if [ ! -d venv ]; then
  python3 -m venv venv
fi
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "🔄 Restarting backend..."
cd ..
./start.sh backend

echo "✅ Deployment finished"
