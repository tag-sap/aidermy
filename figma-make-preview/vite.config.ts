import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

// Основной фронт теперь живёт по корню / (nginx root → static dist).
// base задаёт префикс для asset-ов, чтобы JS/CSS грузились с /assets/...
export default defineConfig({
  base: "/",
  plugins: [react(), tailwindcss()],
})
