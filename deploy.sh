#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "📦 Pulling latest changes from GitHub..."
git pull origin main

echo "📦 Installing frontend dependencies..."
npm install --no-fund --no-audit

echo "🏗️ Building frontend..."
npm run build

echo "🐍 Updating backend dependencies..."
cd backend
if [ ! -d venv ]; then
  python3 -m venv venv
fi
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "🔄 Restarting backend and frontend..."
cd ..
./start.sh all

echo "✅ Deployment finished"
