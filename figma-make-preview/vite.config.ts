import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

// Production preview живёт по пути /ver2/ (nginx alias → static dist).
// base задаёт префикс для asset-ов, чтобы JS/CSS грузились с /ver2/assets/...
export default defineConfig({
  base: "/ver2/",
  plugins: [react(), tailwindcss()],
})
