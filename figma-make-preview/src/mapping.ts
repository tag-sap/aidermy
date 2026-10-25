// mapping.ts — преобразование данных backend (FastAPI) в типы фронтенда V2.
import type { ApiProduct, ShelfItem, EvaluationPreviewStatus } from "./api"
import type { Product, CabinetKey, Verdict, Match, PersonalCheck } from "./data"

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

const LEGACY_VERDICT_ALIASES: Record<string, Verdict> = {
  "Очень хорошо подходит": "Отлично подходит",
  "Подходит": "Хорошо подходит",
  "Скорее не подходит": "Слабо подходит",
  "Нейтральный результат": "Подходит частично",
  "Нейтрально": "Подходит частично",
  "Подходит с оговорками": "Подходит частично",
  "С осторожностью": "Подходит частично",
  "Допустимо": "Подходит частично",
}

export function normalizeVerdict(verdict?: string | null): Verdict | null {
  const value = (verdict || "").trim()
  if (!value) return null
  if (value in LEGACY_VERDICT_ALIASES) return LEGACY_VERDICT_ALIASES[value]
  if (
    value === "Не подходит"
    || value === "Слабо подходит"
    || value === "Подходит частично"
    || value === "Хорошо подходит"
    || value === "Отлично подходит"
    || value === "Не рекомендовано"
  ) return value
  return null
}

export function mapVerdict(score: number | null, backendVerdict?: string): Verdict | null {
  // Новая шкала Score Engine: score определяет диапазон.
  if (score != null) {
    if (score < 20) return "Не подходит"
    if (score < 40) return "Слабо подходит"
    if (score < 60) return "Подходит частично"
    if (score < 80) return "Хорошо подходит"
    return "Отлично подходит"
  }

  // Historical payloads may carry old labels. Display their current equivalent
  // instead of rewriting stored scores or reports.
  return normalizeVerdict(backendVerdict)
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

  const score = typeof a.score === "number" ? a.score : null
  return {
    score,
    verdict: normalizeVerdict(a.verdict) || mapVerdict(score) || undefined,
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
    cabinet: inferCabinet(api.taxonomy_category || category, name),
    category,
    subcategory,
    image: api.image_url || placeholderImage(api.id),
    tags: category ? [category] : [],
    slug: api.slug,
    compositionVerified: api.composition_verified === true,
    ingredients: api.ingredients || "",
    barcode: api.barcode || undefined,
    variant: api.variant || undefined,
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
    verdict: normalizeVerdict(item.verdict) || mapVerdict(score) || undefined,
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
    check: undefined,
  }
}

function previewCheck(raw: EvaluationPreviewStatus): PersonalCheck {
  const status = raw.status === "checked" || raw.status === "stale" ? raw.status : "none"
  return {
    status,
    verdict: raw.verdict || undefined,
    tone: raw.tone || (status === "stale" ? "neutral" : undefined),
    icon: raw.icon || undefined,
    checked_at: raw.checked_at || undefined,
    snapshot_id: raw.snapshot_id || undefined,
    reason: raw.reason || undefined,
  }
}

/**
 * Attach the backend's user-scoped Evaluation V2 status to cards.
 *
 * The status request must be made for the current auth session. A returned
 * ``none``/``stale`` intentionally clears legacy ``match`` data: an old score
 * from another profile or another user must never survive on the card.
 */
export function applyCheckStatuses(
  products: Product[],
  statuses: Record<string, EvaluationPreviewStatus>,
): Product[] {
  return products.map((product) => {
    const raw = statuses[String(product.id)]
    if (!raw) return product
    return {
      ...product,
      match: undefined,
      check: previewCheck(raw),
    }
  })
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
    cabinet: inferCabinet(category, r.name),
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
  // Profile loading is async and this module store is not React state. Notify
  // the mounted app so an open product drawer reloads the saved-report lookup
  // with the real profile instead of an empty initial one.
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("aidermy-profile-updated"))
  }
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
