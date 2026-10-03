// mapping.ts — преобразование данных backend (FastAPI) в типы фронтенда V2.
import type { ApiProduct, ShelfItem } from "./api"
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
  if (backendVerdict === "С осторожностью" || backendVerdict === "Нейтрально") return "Допустимо"
  if (backendVerdict === "Не подходит") return "Не подходит"
  if (score == null) return null
  if (score >= 80) return "Подходит"
  if (score >= 60) return "Допустимо"
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
    ingredients: api.ingredients || "",
  }
}

export function mapShelfItem(item: ShelfItem): Product {
  const { brand, name } = splitProductName(item.name || "", item.brand)
  const score = item.score ?? null
  const verdict = mapVerdict(score)
  return {
    id: item.product_id,
    brand,
    name: name || item.name || "Продукт",
    cabinet: (item.cabinet as CabinetKey) || inferCabinet(item.category, name),
    category: item.category || "",
    score,
    verdict,
    image: item.image_url || placeholderImage(item.product_id),
    tags: item.category ? [item.category] : [],
    state: "using",
    checked: score != null,
    report: item.has_report ?? false,
    slug: item.slug,
    shelf_id: item.shelf_id,
    needs_recheck: item.needs_recheck ?? false,
    ingredients: item.ingredients || "",
  }
}

export function mapHistoryItem(h: { id: number; product_name?: string; score?: number | null; verdict?: string; slug?: string; image_url?: string }): Product {
  const { brand, name } = splitProductName(h.product_name || "", undefined)
  const score = h.score ?? null
  return {
    id: h.id,
    brand,
    name: name || h.product_name || "Продукт",
    cabinet: inferCabinet("", name),
    category: "",
    score,
    verdict: mapVerdict(score, h.verdict),
    image: h.image_url || placeholderImage(h.id),
    tags: [],
    checked: score != null,
    report: false,
    slug: h.slug,
  }
}

function hashSlug(slug: string): number {
  let h = 0
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) | 0
  return Math.abs(h) || 1
}

export function mapRecommendation(r: { id?: number; slug?: string; name?: string; brand?: string; image_url?: string; score?: number | null }, category: string): Product {
  const score = r.score ?? null
  const slug = r.slug || ""
  return {
    id: r.id ?? hashSlug(slug || r.name || "rec"),
    brand: r.brand || "",
    name: r.name || "Продукт",
    cabinet: "face",
    category,
    score,
    verdict: mapVerdict(score),
    image: r.image_url || placeholderImage(r.id ?? hashSlug(slug)),
    tags: category ? [category] : [],
    checked: score != null,
    report: false,
    slug,
  }
}

// Профиль пользователя для /api/check. По умолчанию — демо-профиль,
// но перезаписывается реальными данными анкеты через setUserProfile().
let _userProfile: {
  skinType: string; age: string; concerns: string[]; allergies: string[]; structured: unknown
} = {
  skinType: "Комбинированная",
  age: "25-35",
  concerns: [],
  allergies: [],
  structured: null,
}

export function setUserProfile(p: Partial<typeof _userProfile>) {
  if (p.skinType) _userProfile.skinType = p.skinType
  if (p.age) _userProfile.age = p.age
  if (p.concerns) _userProfile.concerns = p.concerns
  if (p.allergies) _userProfile.allergies = p.allergies
  if (p.structured !== undefined) _userProfile.structured = p.structured
}

export function getUserProfile() {
  return _userProfile
}

export function buildProfile() {
  return {
    name: "",
    age: _userProfile.age || "25-35",
    concerns: _userProfile.concerns || ([] as string[]),
    allergies: _userProfile.allergies || ([] as string[]),
    custom_text: "",
    quiz_answers: null,
    skin_type_determined: null,
    structured: _userProfile.structured || null,
  }
}
