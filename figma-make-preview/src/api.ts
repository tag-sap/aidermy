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
  brand?: string
  rating?: number | null
  rating_count?: number
  score?: number | null
  analysis?: unknown
}

export type CheckResult = {
  score: number
  verdict: string
  summary: string
  pending?: boolean
  safe_ingredients: string[]
  caution_ingredients: string[]
  slug?: string
  image_url?: string
  report?: string
  how_to_use?: { application?: string; time?: string; note?: string }
  expectations?: { when?: string; normal?: string; danger?: string }
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

export type ShelfItem = {
  id: number
  shelf_id: number
  product_id: number
  cabinet: string
  category: string
  added_at?: string
  name: string
  brand?: string
  image_url?: string
  slug?: string
  ingredients?: string
  score?: number | null
  has_report?: boolean
  needs_recheck?: boolean
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
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
  async register(email: string, password: string, name: string) {
    return request<{ message: string; email: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    })
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
    return request<{ status: string; duplicate?: boolean; item?: unknown }>("/shelf", {
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
  async compositionRecognize(payload: Record<string, unknown>) {
    return request("/composition/recognize", { method: "POST", body: JSON.stringify(payload) })
  },
  async check(payload: Record<string, unknown>) {
    return request("/check", { method: "POST", body: JSON.stringify(payload) })
  },
  async checkWithIngredients(payload: Record<string, unknown>) {
    return request<CheckResult>("/check-with-ingredients", { method: "POST", body: JSON.stringify(payload) })
  },
  async analysisReport(slug: string) {
    return request<{ score: number; review: string; active_ingredients?: unknown; how_to_use?: unknown; expectations?: unknown }>("/analysis/report", {
      method: "POST",
      body: JSON.stringify({ slug }),
    })
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
export function setToken(token: string | null) {
  if (typeof window === "undefined") return
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}
