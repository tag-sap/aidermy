// mapping.ts — преобразование данных backend (FastAPI) в типы фронтенда V2.
import type { ApiProduct, ShelfItem } from "./api"
import type { Product, CabinetKey, Verdict, Match } from "./data"

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
  // Новая шкала Score Engine: score определяет диапазон.
  if (score != null) {
    if (score < 20) return "Не подходит"
    if (score < 40) return "Скорее не подходит"
    if (score < 60) return "Нейтральный результат"
    if (score < 80) return "Подходит"
    return "Отлично подходит"
  }

  // Если score отсутствует, сохраняем точный новый вердикт API.
  if (backendVerdict === "Не подходит" ||
      backendVerdict === "Скорее не подходит" ||
      backendVerdict === "Нейтральный результат" ||
      backendVerdict === "Подходит" ||
      backendVerdict === "Отлично подходит") return backendVerdict

  if (backendVerdict === "С осторожностью" ||
      backendVerdict === "Нейтрально" ||
      backendVerdict === "Допустимо") return "Допустимо"

  return null
}

// Собирает отдельный объект Match из сохранённого analysis API.
// score сам по себе НЕ является Match: нужен полноценный analysis с числовым score.
function toMatch(a: {
  id?: number | null
  score?: number | null
  verdict?: string
  summary?: string
  safe_ingredients?: string[]
  caution_ingredients?: string[]
  report?: string | null
  phase1_status?: string | null
  recommendation_status?: string | null
} | null | undefined): Match | undefined {
  if (!a) return undefined
  const hasReport = Boolean(a.report?.trim())
  if (
    typeof a.score !== "number" &&
    typeof a.id !== "number" &&
    !hasReport &&
    !a.phase1_status &&
    !a.recommendation_status
  ) return undefined

  return {
    score: typeof a.score === "number" ? a.score : null,
    verdict: a.verdict || undefined,
    summary: a.summary || undefined,
    safe_ingredients: a.safe_ingredients || undefined,
    caution_ingredients: a.caution_ingredients || undefined,
    report: hasReport ? a.report! : undefined,
    has_report: hasReport,
    analysis_id: typeof a.id === "number" ? a.id : undefined,
    phase1_status: a.phase1_status || undefined,
    recommendation_status: a.recommendation_status || undefined,
  }
}

export function mapApiProduct(api: ApiProduct): Product {
  const { brand, name } = splitProductName(api.name || "", api.brand)
  const category = api.catalog_category || api.category || ""
  const subcategory = api.catalog_subcategory || ""
  return {
    id: api.id,
    brand,
    name: name || "Продукт",
    cabinet: "face",
    category,
    subcategory,
    image: api.image_url || placeholderImage(api.id),
    tags: category ? [category] : [],
    slug: api.slug,
    ingredients: api.ingredients || "",
    match: toMatch(api.analysis as Parameters<typeof toMatch>[0]),
  }
}

export function mapShelfItem(item: ShelfItem): Product {
  const { brand, name } = splitProductName(item.name || "", item.brand)
  const score = item.score ?? null
  const hasReport = item.has_report === true
  const match = (
    score != null ||
    hasReport ||
    item.analysis_id != null ||
    Boolean(item.phase1_status) ||
    Boolean(item.recommendation_status)
  ) ? {
    score,
    verdict: item.verdict || mapVerdict(score) || undefined,
    report: undefined,
    has_report: hasReport,
    analysis_id: item.analysis_id ?? undefined,
    phase1_status: item.phase1_status || undefined,
    recommendation_status: item.recommendation_status || undefined,
    caution_ingredients: item.caution_ingredients || undefined,
  } : undefined
  return {
    id: item.product_id,
    brand,
    name: name || item.name || "Продукт",
    cabinet: (item.cabinet as CabinetKey) || inferCabinet(item.category, name),
    category: item.category || "",
    subcategory: item.subcategory || "",
    image: item.image_url || placeholderImage(item.product_id),
    tags: item.category ? [item.category] : [],
    state: "using",
    slug: item.slug,
    shelf_id: item.shelf_id,
    needs_recheck: item.needs_recheck ?? false,
    ingredients: item.ingredients || "",
    match,
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
    image: h.image_url || placeholderImage(h.id),
    tags: [],
    slug: h.slug,
    match: score != null ? { score, verdict: mapVerdict(score, h.verdict) || undefined } : undefined,
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
    image: r.image_url || placeholderImage(r.id ?? hashSlug(slug)),
    tags: category ? [category] : [],
    slug,
    match: score != null ? { score, verdict: mapVerdict(score) || undefined } : undefined,
  }
}

// Профиль пользователя для /api/check. По умолчанию — демо-профиль,
// но перезаписывается реальными данными анкеты через setUserProfile().
let _userProfile: {
  skinType: string; age: string; concerns: string[]; allergies: string[];
  intolerances: string[]; structured: unknown
} = {
  skinType: "",
  age: "",
  concerns: [],
  allergies: [],
  intolerances: [],
  structured: null,
}

export function setUserProfile(p: Partial<typeof _userProfile>) {
  if (p.skinType) _userProfile.skinType = p.skinType
  if (p.age) _userProfile.age = p.age
  if (p.concerns) _userProfile.concerns = p.concerns
  if (p.allergies) _userProfile.allergies = p.allergies
  if (p.intolerances) _userProfile.intolerances = p.intolerances
  if (p.structured !== undefined) _userProfile.structured = p.structured
}

export function getUserProfile() {
  return _userProfile
}

export function buildProfile() {
  return {
    name: "",
    age: _userProfile.age || "",
    concerns: _userProfile.concerns || ([] as string[]),
    allergies: _userProfile.allergies || ([] as string[]),
    intolerances: _userProfile.intolerances || ([] as string[]),
    custom_text: "",
    quiz_answers: null,
    skin_type_determined: null,
    structured: _userProfile.structured || null,
  }
}
