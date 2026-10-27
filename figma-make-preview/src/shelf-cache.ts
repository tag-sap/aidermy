import type { Plan, Product } from "./data"

export type ShelfMeta = {
  plan: Plan
  limit: number
  setLimit: number
  count: number
}

export type CachedShelf = {
  items: Product[]
  meta: ShelfMeta
  savedAt: number
}

// v2 invalidates cached cards created by the old photo flow, which persisted
// a placeholder ``match: {score: null}`` and could show a stale verdict.
const PREFIX = "aidermy:shelf:v2:"
const MAX_AGE_MS = 24 * 60 * 60 * 1000

function key(userId: number) {
  return `${PREFIX}${userId}`
}

export function readShelfCache(userId?: number | null): CachedShelf | null {
  if (!userId || typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(key(userId))
    if (!raw) return null
    const value = JSON.parse(raw) as CachedShelf
    if (!value || !Array.isArray(value.items) || !value.meta) return null
    if (!value.savedAt || Date.now() - value.savedAt > MAX_AGE_MS) {
      window.sessionStorage.removeItem(key(userId))
      return null
    }
    // Defensive migration for snapshots written by an older build.
    value.items = value.items.map((item) => ({
      ...item,
      match: item.match && typeof item.match.score === "number" ? item.match : undefined,
    }))
    return value
  } catch {
    return null
  }
}

export function writeShelfCache(userId: number | undefined, items: Product[], meta: ShelfMeta) {
  if (!userId || typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(
      key(userId),
      JSON.stringify({ items, meta, savedAt: Date.now() } satisfies CachedShelf),
    )
  } catch {
    // Storage can be unavailable/private. The live server remains authoritative.
  }
}

export function clearShelfCache(userId?: number | null) {
  if (typeof window === "undefined") return
  try {
    if (userId) {
      window.sessionStorage.removeItem(key(userId))
      return
    }
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const name = window.sessionStorage.key(index)
      if (name?.startsWith(PREFIX)) window.sessionStorage.removeItem(name)
    }
  } catch {
    // Nothing to clear.
  }
}
