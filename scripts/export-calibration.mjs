#!/usr/bin/env node
// export-calibration.mjs
// Кросс-платформенная обёртка над backend/app/export_calibration.py.
// Находит venv-интерпретатор (Windows/ПОСИКС) и запускает экспорт, пробрасывая
// аргументы (--count / --seed / --out / --format) и принудительно выставляя UTF-8.

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const backend = path.join(root, "backend");

function resolvePython() {
  const candidates = [
    path.join(backend, "venv", "Scripts", "python.exe"), // Windows
    path.join(backend, "venv", "bin", "python"), // ПОСИКС
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return "python3";
}

const python = resolvePython();
const args = process.argv.slice(2);

const hasOut = args.some((a) => a === "--out" || a.startsWith("--out="));
const finalArgs = hasOut ? [...args] : [...args, "--out", path.join(root, "calibration")];

const result = spawnSync(python, ["-m", "app.export_calibration", ...finalArgs], {
  cwd: backend,
  stdio: "inherit",
  env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
});

process.exit(result.status ?? 1);
