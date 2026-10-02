// mapping.ts — преобразование данных backend (FastAPI) в типы фронтенда V2.
import type { ApiProduct } from "./api"
import type { Product, CabinetKey, Verdict } from "./data"

function placeholderImage(id: number): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#f0f0f0"/><text x="100" y="105" font-size="30" text-anchor="middle" fill="#bbb">${id}</text></svg>`)}`
}

export function inferCabinet(category?: string, name?: string): CabinetKey {
  const c = `${category || ""} ${name || ""}`.toLowerCase()
  if (/шампунь|бальзам|кондиционер|волос|масло для волос/.test(c)) return "hair"
  if (/дезодорант|для душа|гель для душа|для тела|крем для тела|для рук|для ног|мыло|скраб для тела|body/.test(c)) return "body"
  if (/тушь|помада|тональн|консилер|пудра|румяна|тени|макияж|makeup/.test(c)) return "makeup"
  if (/парфюм|туалетная вода|парфюмерная вода|одеколон|fragrance/.test(c)) return "fragrance"
  return "face"
}

export function splitProductName(raw: string, brand?: string): { brand: string; name: string } {
  const parts = (raw || "").split("\n").map((s) => s.trim()).filter(Boolean)
  const b = (brand || "").trim() || (parts.length >= 2 ? parts[0] : "")
  const n = parts.length >= 2 ? parts.slice(1).join(" ") : (parts[0] || raw || "")
  return { brand: b, name: n || raw || "" }
}

export function mapVerdict(score: number | null, backendVerdict?: string): Verdict | null {
  if (backendVerdict === "Подходит") return "Подходит"
  if (backendVerdict === "С осторожностью" || backendVerdict === "Нейтрально") return "Осторожно"
  if (backendVerdict === "Не подходит") return "Не подходит"
  if (score == null) return null
  if (score >= 80) return "Подходит"
  if (score >= 60) return "Осторожно"
  return "Не подходит"
}

export function mapApiProduct(api: ApiProduct): Product {
  const { brand, name } = splitProductName(api.name || "", api.brand)
  const category = api.taxonomy_category || api.category || ""
  const score = api.score ?? null
  const verdict = mapVerdict(score)
  return {
    id: api.id,
    brand,
    name: name || "Продукт",
    cabinet: inferCabinet(category, name),
    category,
    score,
    verdict,
    image: api.image_url || placeholderImage(api.id),
    tags: category ? [category] : [],
    checked: score != null,
    report: false,
    slug: api.slug,
  }
}

// Профиль для /api/check — собирается из статичного skinProfile (демо).
export function buildProfile() {
  return {
    name: "",
    age: "25-35",
    concerns: [] as string[],
    allergies: [] as string[],
    custom_text: "",
    quiz_answers: null,
    skin_type_determined: null,
    structured: null,
  }
}
