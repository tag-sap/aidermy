// api.ts — клиент к реальному backend (FastAPI).
// BASE = "/api" — nginx проксирует /api/ на 127.0.0.1:8000, поэтому работает
// и на /ver2/ (сейчас), и с корня (после миграции).

const BASE = "/api"

export const TOKEN_KEY = "aidermy_token"

export type ApiUser = {
  id: number
  email: string
  name: string
  skin_type?: string | null
  age?: string | null
  concerns?: string[]
  allergies?: string[]
  avatar_url?: string | null
  balance?: number
  plan?: string
}

export type ApiProduct = {
  id: number
  name: string
  slug: string
  image_url: string
  ingredients?: string
  category?: string
  subcategory?: string
  taxonomy_category?: string
  catalog_category?: string
  catalog_subcategory?: string
  brand?: string
  barcode?: string
  variant?: string
  rating?: number | null
  rating_count?: number
  score?: number | null
  verified?: boolean
  analysis?: unknown
}

export type ScanProductPayload = {
  id?: number
  name: string
  slug?: string
  brand?: string
  image_url?: string
  category?: string
  ingredients?: string
  barcode?: string
  variant?: string
  ingredients_source?: string
  source_url?: string
  has_inci?: boolean
}

export type ScanCandidatePayload = ScanProductPayload & {
  match_score?: number
  has_inci?: boolean
}

export type ScanDraftPayload = {
  id?: number | null
  slug?: string
  brand?: string
  name?: string
  variant?: string | null
  type?: string | null
  volume?: string | null
  barcode?: string | null
  ingredients: string
  ingredients_source: string
  source_url?: string
  image_url?: string
}

export type CheckResult = {
  score: number | null
  verdict: string
  summary: string
  pending?: boolean
  safe_ingredients: string[]
  caution_ingredients: string[]
  slug?: string
  image_url?: string
  analysis_id?: number
  report?: string
  how_to_use?: { application?: string; time?: string; note?: string }
  expectations?: { when?: string; normal?: string; danger?: string }
  phase1_status?: string
  recommendation_status?: string
  phase1_violations?: { axis: string; load: number; threshold: number | null; violated: boolean }[]
  negative_only_score?: number
  product_id?: number
  product_context?: {
    signals?: {
      signal_id?: string
      ingredient?: string
      axis?: string
      direction?: string
      effect_value?: number
      evidence_refs?: string[]
    }[]
  } | null
  product_knowledge?: {
    scoring_signals?: {
      signal_id?: string
      ingredient?: string
      axis?: string
      direction?: string
      evidence_quote?: string
      source_urls?: string[]
    }[]
  } | null
}

export type ReportFragment = { text: string; sentiment: "positive" | "negative" }

export type ReportIngredient = {
  name: string
  inci_name?: string
  function?: string
  skin_effects?: string
  role?: string
  evidence_level?: string
  sources?: string
  direction?: "positive" | "negative" | "neutral"
  unknown?: boolean
  is_key?: boolean
}

export type ReportDetail = {
  version?: string
  data_quality?: { known_ingredients?: number; unknown_ingredients?: number; total_ingredients?: number; coverage?: number; confidence?: number; label?: string }
  sections?: { id: string; title: string; basis?: string; paragraphs?: string[] }[]
  key_ingredients?: ReportIngredient[]
  other_ingredients?: ReportIngredient[]
  interactions?: Record<string, unknown>[]
}

export type ReportResult = {
  score: number | null
  verdict?: string | null
  phase1_status?: string | null
  recommendation_status?: string | null
  report_ready?: boolean
  review?: ReportFragment[]
  active_ingredients?: unknown
  what_good?: ReportFragment[]
  what_bad?: ReportFragment[]
  how_to_use?: { application?: string; time?: string; note?: string } | null
  expectations?: { when?: string; normal?: string; danger?: string } | null
  inci?: string[]
  category?: string
  details?: ReportDetail | null
}

export type Review = {
  id: number
  product_id: number
  user_id?: number | null
  author_name?: string
  rating: number
  text?: string
  is_anonymous?: boolean
  created_at?: string
}

// ===== Evaluation V2 (per-parameter analysis) =====
// Включается только на серверах, где развёрнут Evaluation V2 и задан
// VITE_EVALUATION_V2=1. По умолчанию выключено: текущий отчёт продолжает работать.
export const EVALUATION_V2_ENABLED = String(import.meta.env.VITE_EVALUATION_V2 ?? "") === "1"

export type EvaluationGap = {
  parameter_id: string
  reason: "missing" | "stale" | "insufficient" | "unsupported" | string
  detail?: string
}

export type EvaluationAnalysis = {
  status: "complete" | "incomplete" | "failed" | "blocked" | string
  is_final: boolean
  assessed_parameters: string[]
  not_applicable_parameters: string[]
  gaps: EvaluationGap[]
  failed_parameters: string[]
  deferred_parameters: string[]
  exhausted_parameters: string[]
  documents_fetched: number
  documents_reused: number
  notes: string[]
}

export type EvaluationComposition = {
  hash?: string
  composition_hash?: string
  source?: string
  verified_at?: string
  status?: string
  inci_raw?: string
}

export type EvaluationCompositionState = {
  usable: boolean
  reason: "confirmed" | "trusted_catalog" | "untrusted_source" | "source_missing" | "incomplete" | "missing" | string
  action: "none" | "check_source" | "provide_inci" | string
  trust: string
  message: string
  source_host?: string
  auto_verify?: boolean
}

export type EvaluationEvidence = {
  id: number
  parameter_id: string
  claim: string
  quote: string
  verification: string
  provenance?: string
  source: { url: string; title?: string; publisher?: string; source_type?: string }
}

export type EvaluationParameterRow = {
  parameter_id: string
  label?: string
  value: number
  status: string
  included: boolean
  weight: number
  reason: string
  summary?: string
}

export type EvaluationPrimaryFunction = {
  label: string
  purpose: string
  score: number | null
  reason: string
  basis?: Array<{
    type?: string
    label: string
    value: string
    source?: string
  }>
}

export type EvaluationIntoleranceStatus = {
  state: "present" | "absent" | "unknown" | string
  label: string
  status: string
  reason?: string
  matched?: string[]
}

export type EvaluationVerdict = "positive" | "neutral" | "negative" | "unknown"

export type EvaluationOverall = {
  verdict: "Подходит" | "Подходит с оговорками" | "Не подходит" | "Недостаточно данных" | string
  tone: "good" | "warn" | "bad" | "muted" | string
  summary: string
  positive: number
  neutral: number
  negative: number
  unknown: number
  assessed: number
}

export type EvaluationPersonalParameter = {
  parameter_id: string
  label: string
  score: number | null
  reason: string
  evidence?: EvaluationEvidence[]
  intolerance?: EvaluationIntoleranceStatus
  section?: string
  verdict?: EvaluationVerdict
  verdict_label?: string
  display_text?: string
  verdict_icon?: "check" | "dash" | "cross" | string
}

export type EvaluationUserReport = {
  product_name: string
  primary_function: EvaluationPrimaryFunction
  overall: EvaluationOverall
  personal_compatibility: EvaluationPersonalParameter[]
  sources: string[]
}

export type EvaluationSnapshot = {
  snapshot_id: string
  product: { id: number; name: string }
  composition: EvaluationComposition
  parameters: EvaluationParameterRow[]
  total: number | null
  verdict: string | null
  completeness: number
  analysis: EvaluationAnalysis
  limitations: string[]
  created_at: string
}

export type EvaluationReport = {
  product: { id: number; name: string; brand?: string }
  composition: EvaluationComposition
  composition_state?: EvaluationCompositionState
  snapshot: EvaluationSnapshot
  analysis: EvaluationAnalysis
  evidence?: Record<string, EvaluationEvidence[]>
  primary_function?: EvaluationPrimaryFunction
  user_report?: EvaluationUserReport
  plan?: { needed: string[]; stale: string[]; gaps: EvaluationGap[]; blocked: boolean; notes: string[] }
  research?: { documents_fetched: number; documents_reused: number; cost_usd: number; failed: string[]; notes: string[] }
}

export type EvaluationSavedReport = {
  saved: boolean
  reason?: string
  report: EvaluationReport | null
}

export type EvaluationProductStatus = {
  product: { id: number; name: string; brand?: string; url?: string; has_reliable_inci?: boolean }
  composition: EvaluationComposition
  composition_state?: EvaluationCompositionState
  analysis: EvaluationAnalysis
  current: Array<{ parameter_id: string; status: string; value: number | null; rationale: string }>
  source_urls: string[]
  snapshot?: EvaluationSnapshot | null
}

export type EvaluationCompositionCheck = {
  checked: boolean
  composition: EvaluationComposition
  composition_state: EvaluationCompositionState
  message: string
}

export type ShelfItem = {
  id: number
  shelf_id: number
  product_id: number
  cabinet: string
  category: string
  subcategory?: string
  added_at?: string
  name: string
  brand?: string
  image_url?: string
  slug?: string
  ingredients?: string
  score?: number | null
  analysis_id?: number | null
  phase1_status?: string | null
  recommendation_status?: string | null
  verdict?: string | null
  has_report?: boolean
  needs_recheck?: boolean
  caution_ingredients?: string[]
}

export type ShelfCategory = { key: string; title: string; items: ShelfItem[]; compatibility?: number | null }
export type ShelfCabinet = {
  key: string
  title: string
  has_scoring: boolean
  compatibility?: number | null
  categories: ShelfCategory[]
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

let _refreshPromise: Promise<boolean> | null = null

// Продление сессии по действующему токену. Один общий промис: параллельные
// 401 не порождают лавину refresh-запросов.
export function refreshSession(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise
  const epoch = _sessionEpoch
  _refreshPromise = (async () => {
    const token = getToken()
    if (!token) return false
    try {
      const res = await fetch(BASE + "/auth/refresh", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) return false
      const data = (await res.json()) as { access_token?: string }
      if (data && data.access_token) {
        // Пользователь вышел, пока шёл refresh — не воскрешаем сессию.
        if (epoch !== _sessionEpoch || !getToken()) return false
        setToken(data.access_token)
        return true
      }
      return false
    } catch {
      return false
    }
  })()
  _refreshPromise.finally(() => { _refreshPromise = null })
  return _refreshPromise
}

async function request<T>(path: string, options: RequestInit = {}, _retried = false): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> | undefined) }
  const token = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null
  if (token) headers["Authorization"] = `Bearer ${token}`
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json"

  let res: Response
  try {
    res = await fetch(BASE + path, { ...options, headers })
  } catch {
    throw new ApiError("Нет соединения с сервером", 0)
  }

  if (!res.ok) {
    if (res.status === 401 && !_retried && !path.startsWith("/auth/")) {
      // Access token истёк — пробуем продлить сессию один раз и повторить.
      const renewed = await refreshSession()
      if (renewed) return request<T>(path, options, true)
    }
    let detail = `Ошибка ${res.status}`
    try {
      const data = await res.json()
      detail = (data as { detail?: string; message?: string }).detail || (data as { message?: string }).message || detail
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  // ===== auth =====
  async register(email: string, password: string, name: string, acceptOffer = false) {
    return request<{
      verification_required?: boolean
      message?: string
      email?: string
      access_token?: string
      token_type?: string
      user?: ApiUser
    }>("/auth/register", {
      method: "POST",
      // Согласие с офертой передаётся явным флагом; сервер фиксирует его сам.
      body: JSON.stringify({ email, password, name, accept_offer: acceptOffer }),
    })
  },
  async recordConsent(consentType: string, context = "") {
    return request<{ status: string }>("/auth/consents", {
      method: "POST",
      body: JSON.stringify({ consent_type: consentType, context }),
    })
  },
  async deleteAccount(confirm: string, password?: string) {
    return request<{ status: string; deleted: Record<string, number> }>("/auth/account/delete", {
      method: "POST",
      body: JSON.stringify({ confirm, password }),
    })
  },
  async billingCatalog() {
    return request<{
      provider: string
      currency: string
      prices_defined: boolean
      payments_configured: boolean
      plans: { key: string; title: string; monthly_points: number; price: number | null; available: boolean }[]
      packages: { id: string; title: string; checks?: number | null; price?: number | null }[]
      note: string
    }>("/billing/catalog")
  },
  async createOrder(payload: { plan: string; kind?: string }) {
    return request<{ status: string }>("/billing/orders", {
      method: "POST",
      body: JSON.stringify({ kind: "subscription", ...payload }),
    })
  },
  async refresh() {
    return request<{ access_token: string; token_type: string; user: ApiUser }>("/auth/refresh", {
      method: "POST",
    })
  },
  // Загрузка фото продукта (multipart). Content-Type НЕ задаём вручную:
  // браузер сам проставит boundary; сервер проверяет реальный формат по байтам.
  async uploadProductImage(file: File) {
    const token = getToken()
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    let res: Response
    try {
      res = await fetch(BASE + "/uploads/product-image", { method: "POST", headers, body: (() => {
        const form = new FormData()
        form.append("file", file)
        return form
      })() })
    } catch {
      throw new ApiError("Нет соединения с сервером", 0)
    }
    if (!res.ok) {
      let detail = `Ошибка ${res.status}`
      try {
        const data = await res.json() as { detail?: string }
        if (data && data.detail) detail = data.detail
      } catch { /* ignore */ }
      throw new ApiError(detail, res.status)
    }
    return (await res.json()) as { url: string; key: string }
  },
  async login(email: string, password: string) {
    const body = new URLSearchParams({ username: email, password })
    return request<{ access_token: string; token_type: string; user: ApiUser }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    })
  },
  async me() {
    return request<ApiUser>("/auth/me")
  },
  async saveProfile(profile: Record<string, unknown>) {
    return request<{
      status: string
      profile?: {
        skinType?: string
        allergies?: string[]
        intolerances?: string[]
        structuredProfile?: Record<string, unknown>
      } | null
    }>("/auth/profile", {
      method: "POST",
      body: JSON.stringify({ profile }),
    })
  },
  async getProfile() {
    return request<{ profile?: Record<string, unknown>; structured?: Record<string, unknown> }>("/auth/profile/me")
  },

  // ===== баланс / подписка =====
  async balance() {
    return request<{ balance: number; plan: string; monthly_points: number }>("/balance")
  },
  async topUp(amount: number) {
    return request<{ balance: number; plan: string; monthly_points: number }>("/balance/topup", {
      method: "POST",
      body: JSON.stringify({ amount }),
    })
  },
  async subscription(plan: string) {
    return request<{ balance: number; plan: string; monthly_points: number }>("/subscription", {
      method: "POST",
      body: JSON.stringify({ plan }),
    })
  },

  // ===== каталог / продукты =====
  async catalog(params: Record<string, string | number> = {}) {
    const qs = new URLSearchParams(params as Record<string, string>).toString()
    return request<{ products: ApiProduct[]; total: number; limit: number; offset: number }>(`/catalog${qs ? "?" + qs : ""}`)
  },
  async products(q = "") {
    return request<{ products: ApiProduct[] }>(`/products?q=${encodeURIComponent(q)}`)
  },
  async product(slug: string) {
    return request<{ product: ApiProduct; score: number | null; analysis: unknown; on_shelf: unknown; community: unknown }>(`/products/${slug}`)
  },

  // ===== полка =====
  async shelf() {
    return request<{ cabinets: ShelfCabinet[] }>("/shelf")
  },
  async addToShelf(slug: string, category: string, cabinet: string) {
    return request<{ status: string; duplicate?: boolean; item?: { id?: number; product_id?: number } }>("/shelf", {
      method: "POST",
      body: JSON.stringify({ slug, category, cabinet }),
    })
  },
  async removeFromShelf(shelfId: number) {
    return request<{ status: string; deleted?: number }>(`/shelf/${shelfId}`, { method: "DELETE" })
  },
  async clearShelf(cabinet: string, category = "") {
    return request<{ status: string; deleted?: number }>("/shelf/clear", {
      method: "POST",
      body: JSON.stringify({ cabinet, category }),
    })
  },
  async resetShelf() {
    return request<{ status: string; deleted?: number }>("/shelf/reset", { method: "POST", body: "{}" })
  },
  async removalFeedback(slug: string, reason: string) {
    return request("/shelf/removal-feedback", { method: "POST", body: JSON.stringify({ slug, reason }) })
  },
  async deleteBatch(ids: number[]) {
    return request<{ status: string; deleted?: number }>("/shelf/delete-batch", { method: "POST", body: JSON.stringify({ ids }) })
  },
  async recheck(productId: number) {
    return request<{ score: number; analysis: unknown }>(`/shelf/recheck/${productId}`, { method: "POST" })
  },
  async updateShelfCategory(shelfId: number, category: string) {
    return request(`/shelf/${shelfId}`, { method: "PATCH", body: JSON.stringify({ category }) })
  },
  async shelfRecommend(cabinet: string, category: string) {
    return request<{ cabinet: string; category: string; recommendations: ApiProduct[] }>("/shelf/recommend", { method: "POST", body: JSON.stringify({ cabinet, category }) })
  },
  async history() {
    return request<unknown[]>("/auth/history")
  },

  // ===== скан по ссылке =====
  async importUrl(url: string) {
    return request<{ success: boolean; product: { name?: string; brand?: string; image_url?: string; category?: string; ingredients_raw?: string; slug?: string; id?: number } }>("/products/import-url", {
      method: "POST",
      body: JSON.stringify({ url }),
    })
  },

  // ===== сканирование / проверка =====
  async identify(payload: Record<string, unknown>) {
    return request("/product/identify", { method: "POST", body: JSON.stringify(payload) })
  },
  async scanProduct(payload: { front_image: string; back_images: string[] }) {
    return request<{
      status: "ready" | "ambiguous" | "needs_confirmation" | "not_found"
      message?: string
      product?: ScanProductPayload
      candidates?: ScanCandidatePayload[]
      draft?: ScanDraftPayload | null
      can_analyze?: boolean
      warnings?: string[]
      identified?: {
        brand?: string
        product_name?: string
        variant?: string | null
        type?: string | null
        volume?: string | null
        barcode?: string | null
        missing_fields?: string[]
      }
    }>("/product/scan", { method: "POST", body: JSON.stringify(payload) })
  },
  async createProduct(payload: {
    brand?: string
    name: string
    ingredients?: string[]
    slug?: string
    image_data_url?: string
    source_url?: string
    volume?: string
    variant?: string
    barcode?: string
    category?: string
    source_type?: string
  }) {
    return request<{ success: boolean; duplicate?: boolean; product: ScanProductPayload }>("/products/create", {
      method: "POST",
      body: JSON.stringify(payload),
    })
  },
  async compositionRecognize(payload: Record<string, unknown>) {
    return request("/composition/recognize", { method: "POST", body: JSON.stringify(payload) })
  },
  // Гостевой сценарий: одна проверка одного средства за сеанс.
  async guestSession(profile: Record<string, unknown>) {
    return request<{ guest_token: string; expires_at: string; ttl_minutes: number }>("/guest/session", {
      method: "POST",
      body: JSON.stringify({ profile }),
    })
  },
  async guestReport(guestToken: string) {
    return request<ReportResult>("/guest/report", {
      method: "POST",
      body: JSON.stringify({ guest_token: guestToken }),
    })
  },
  async guestClaim(guestToken: string) {
    return request<{ status: string; analysis_id?: number; already_claimed: boolean }>("/guest/claim", {
      method: "POST",
      body: JSON.stringify({ guest_token: guestToken }),
    })
  },
  async check(payload: Record<string, unknown>) {
    return request<CheckResult>("/check", { method: "POST", body: JSON.stringify(payload) })
  },
  async checkWithIngredients(payload: Record<string, unknown>) {
    return request<CheckResult>("/check-with-ingredients", { method: "POST", body: JSON.stringify(payload) })
  },
  async analysisReport(slug: string, analysisId?: number) {
    return request<ReportResult>("/analysis/report", {
      method: "POST",
      body: JSON.stringify({ slug, analysis_id: analysisId ?? null }),
    })
  },

  // ===== evaluation v2 =====
  // Статус/анализ не тратят деньги на исследование: /research — только админ.
  async evaluationHealth() {
    return request<{ storage?: { configured?: boolean }; research?: Record<string, string>; schema?: Record<string, unknown> }>(
      "/v1/evaluation/health"
    )
  },
  async evaluationProductStatus(productId: number, profile: Record<string, unknown>) {
    return request<EvaluationProductStatus>(`/v1/evaluation/products/${productId}/status`, {
      method: "POST",
      body: JSON.stringify({ profile }),
    })
  },
  async evaluationProductSavedReport(productId: number, profile: Record<string, unknown>) {
    return request<EvaluationSavedReport>(`/v1/evaluation/products/${productId}/saved-report`, {
      method: "POST",
      body: JSON.stringify({ profile }),
    })
  },
  async evaluationProductAnalyze(productId: number, profile: Record<string, unknown>) {
    return request<EvaluationReport>(`/v1/evaluation/products/${productId}/analyze`, {
      method: "POST",
      body: JSON.stringify({ profile }),
    })
  },
  async evaluationProductEvaluate(productId: number, profile: Record<string, unknown>) {
    return request<EvaluationReport>(`/v1/evaluation/products/${productId}/evaluate`, {
      method: "POST",
      body: JSON.stringify({ profile }),
    })
  },
  async evaluationCompositionCheck(productId: number, sourceUrl?: string) {
    return request<EvaluationCompositionCheck>(
      `/v1/evaluation/products/${productId}/composition/check`,
      {
        method: "POST",
        body: JSON.stringify({ source_url: sourceUrl || "" }),
      }
    )
  },
  async evaluationSnapshot(snapshotId: string) {
    return request<{ snapshot: EvaluationSnapshot }>(
      `/v1/evaluation/snapshots/${encodeURIComponent(snapshotId)}`
    )
  },

  // ===== отзывы =====
  async reviews(slug: string) {
    return request<{ reviews: Review[] }>(`/community/reviews?slug=${encodeURIComponent(slug)}`)
  },
  async addReview(slug: string, rating: number, text: string, anonymous: boolean) {
    return request("/community/reviews", {
      method: "POST",
      body: JSON.stringify({ slug, rating, text, visibility: anonymous ? "ANONYMOUS" : "PUBLIC" }),
    })
  },
}

export function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null
}
// Поколение сессии: logout инвалидирует уже запущенные refresh-запросы,
// чтобы поздний ответ не вернул токен обратно после выхода.
let _sessionEpoch = 0

export function setToken(token: string | null) {
  if (typeof window === "undefined") return
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    _sessionEpoch += 1
    localStorage.removeItem(TOKEN_KEY)
  }
}

// ===== СБОРКИ УХОДА (care sets) =====

export type CareSetSummary = {
  id: number
  name: string
  source: string
  template_id?: number | null
  item_count: number
  created_at?: string
  updated_at?: string
}

export type CareSetItem = {
  item_id: number
  id: number
  slug: string
  name: string
  brand: string
  image_url: string
  category: string
  score: number | null
}

export type CareSetCompatibility = {
  score: number | null
  coverage?: { scored: number; total: number }
  scores?: { slug: string; name: string; score: number }[]
  conflicts?: { label: string; products: string[] }[]
  note?: string
}

export type CareSetDetail = {
  id: number
  name: string
  source: string
  template_id?: number | null
  items: CareSetItem[]
  profile_compatibility: CareSetCompatibility
  products_compatibility: CareSetCompatibility
}

export type CareSetTemplate = { id: number; slug: string; title: string; description: string }

export type CareSetTemplateStep = {
  id: number
  category: string
  subcategory: string
  position: number
  is_optional: boolean
  candidates_count: number
  config: string
}

export type CareSetTemplateDetail = {
  id: number
  slug: string
  title: string
  description: string
  steps: CareSetTemplateStep[]
}

export type CareSetCandidate = {
  id: number
  slug: string
  name: string
  brand: string
  image_url: string
  category: string
  score: number | null
}

export const careSetsApi = {
  async list() {
    return request<{ sets: CareSetSummary[] }>("/care-sets")
  },
  async create(name: string, source = "manual", items: { slug: string }[] = []) {
    return request<{ id: number; added: number }>("/care-sets", {
      method: "POST",
      body: JSON.stringify({ name, source, items }),
    })
  },
  async detail(id: number) {
    return request<CareSetDetail>(`/care-sets/${id}`)
  },
  async rename(id: number, name: string) {
    return request<{ status: string }>(`/care-sets/${id}`, { method: "PATCH", body: JSON.stringify({ name }) })
  },
  async remove(id: number) {
    return request<{ status: string }>(`/care-sets/${id}`, { method: "DELETE" })
  },
  async addItem(id: number, slug: string) {
    return request<{ status: string; duplicate?: boolean }>(`/care-sets/${id}/items`, {
      method: "POST",
      body: JSON.stringify({ slug }),
    })
  },
  async removeItem(id: number, itemId: number) {
    return request<{ status: string }>(`/care-sets/${id}/items/${itemId}`, { method: "DELETE" })
  },
  async reorder(id: number, orderedItemIds: number[]) {
    return request<{ status: string }>(`/care-sets/${id}/items/reorder`, {
      method: "PATCH",
      body: JSON.stringify({ ordered_item_ids: orderedItemIds }),
    })
  },
  async templates() {
    return request<{ templates: CareSetTemplate[] }>("/care-set-templates")
  },
  async template(slug: string) {
    return request<CareSetTemplateDetail>(`/care-set-templates/${slug}`)
  },
  async candidates(slug: string, stepIndex: number, excludeSlugs: string[] = []) {
    return request<{ step: number; category: string; is_optional: boolean; candidates: CareSetCandidate[] }>(
      `/care-set-templates/${slug}/candidates`,
      { method: "POST", body: JSON.stringify({ step_index: stepIndex, exclude_slugs: excludeSlugs }) },
    )
  },
}
