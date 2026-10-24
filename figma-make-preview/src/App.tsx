import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from "react"
import loadingGif from "./assets/loading.gif"
import fingerLeft from "./assets/autopick/Finger Left-r-s_iconoteka.svg"
import fingerRight from "./assets/autopick/Finger Right-r-s_iconoteka.svg"
import { api, ApiError, EVALUATION_V2_ENABLED, setToken, getToken, type ApiProduct, type ReportResult, type Review } from "./api"
import { LegalPage, SiteFooter, legalDocFromPath } from "./legal"
import { CareSetsPage } from "./careSets"
import { mapApiProduct, mapShelfItem, mapRecommendation, mapVerdict, normalizeVerdict, buildProfile, setUserProfile, getUserProfile } from "./mapping"
import { PhotoScan } from "./photo-scan"
import { ReportDetails } from "./report-details"
import { EvaluationV2Panel } from "./evaluation-v2"
import { AnimatedBorderWrapper } from "./components/ui/moving-border"
import {
  products, skinProfile, shelfReport, CABINETS, FACE_TAXONOMY, PLANS, SUBSCRIPTION_ROWS, EXTRA_POINTS_NOTE,
  SKIN_TYPE_OPTIONS, AGE_OPTIONS, CONCERN_CARDS, THERAPY_OPTIONS, RETINOID_OPTIONS,
  ACID_OPTIONS, PROCEDURE_OPTIONS, PROCEDURE_PERIODS, INTOLERANCE_OPTIONS, GOALS_OPTIONS,
  type Page, type Product, type ProductState, type Verdict, type Plan, type CabinetKey,
  type QuizBranch, type QuizOption,
} from "./data"

type User = { name: string; initials: string; plan: Plan; points: number }

type IconName =
  | "home" | "shelf" | "scan" | "search" | "chart" | "user"
  | "arrow" | "chevron" | "close" | "check" | "plus" | "sparkle"
  | "drop" | "shield" | "file" | "bookmark" | "box" | "alert" | "camera" | "upload" | "back"
  | "link" | "pencil" | "coins" | "crown" | "logout" | "lock" | "send" | "mail" | "credits"

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    home: (<><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-6h6v6" /></>),
    shelf: (<><path d="M4 4h6v16H4zM14 4h6v16h-6z" /><path d="M6.5 9h1M16.5 9h1" /></>),
    scan: (<><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" /><path d="M7 12h10" /></>),
    search: (<><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>),
    chart: (<><path d="M4 20V10M10 20V4M16 20v-6M21 20H3" /></>),
    user: (<><circle cx="12" cy="8" r="4" /><path d="M4 20c0-3 3-5 8-5s8 2 8 5" /></>),
    arrow: (<><path d="M5 12h14M13 6l6 6-6 6" /></>),
    back: (<><path d="M19 12H5M11 6l-6 6 6 6" /></>),
    chevron: (<path d="m9 6 6 6-6 6" />),
    close: (<path d="M18 6 6 18M6 6l12 12" />),
    check: (<path d="m5 12 4 4L19 6" />),
    plus: (<path d="M12 5v14M5 12h14" />),
    sparkle: (<path d="M12 3l1.7 4.6L18 9l-4.3 1.4L12 15l-1.7-4.6L6 9l4.3-1.4L12 3zM19 14l.9 2.4L22 17l-2.1.6L19 20l-.9-2.4L16 17l2.1-.6L19 14z" />),
    drop: (<path d="M12 3s6 5.5 6 10a6 6 0 0 1-12 0c0-4.5 6-10 6-10z" />),
    shield: (<><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" /><path d="m9 12 2 2 4-4" /></>),
    file: (<><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 13h6M9 17h6" /></>),
    bookmark: (<path d="M6 3h12v18l-6-4-6 4z" />),
    box: (<><path d="M21 8 12 3 3 8v8l9 5 9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></>),
    alert: (<><path d="M12 3 2 20h20L12 3z" /><path d="M12 9v5M12 17.5v.5" /></>),
    camera: (<><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></>),
    upload: (<><path d="M12 16V4M6 10l6-6 6 6" /><path d="M4 20h16" /></>),
    link: (<><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.5 1.5" /><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.5-1.5" /></>),
    pencil: (<><path d="M4 20h4L19 9l-4-4L4 16v4z" /><path d="m13 7 4 4" /></>),
    coins: (<><circle cx="9" cy="12" r="6" /><path d="M9 6v12M15 12h6M12 9h6" /></>),
    credits: (<path fill="currentColor" stroke="none" d="M12.0005 22C6.40049 22 2.00049 17.6 2.00049 12C2.00049 6.4 6.40049 2 12.0005 2C17.6005 2 22.0005 6.4 22.0005 12C22.0005 17.6 17.6005 22 12.0005 22ZM12.0005 20.15C16.5505 20.15 20.1005 16.6 20.1005 12C20.1005 7.4 16.5505 3.85 12.0005 3.85C7.45049 3.85 3.90049 7.4 3.90049 12C3.90049 16.6 7.45049 20.15 12.0005 20.15ZM14.4505 12C13.4755 11.3 12.7255 10.525 12.0005 9.6C11.2755 10.525 10.5255 11.3 9.55049 12C10.5255 12.7 11.2755 13.475 12.0005 14.4C12.7255 13.475 13.4755 12.7 14.4505 12ZM17.6255 12C14.9755 13.125 13.1255 14.975 12.0005 17.625C10.8755 14.975 9.02549 13.125 6.37549 12C9.02549 10.875 10.8755 9.025 12.0005 6.375C13.1255 9.025 14.9755 10.875 17.6255 12Z" />),
    crown: (<path d="M4 7l4 4 4-6 4 6 4-4-2 12H6L4 7z" />),
    logout: (<><path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4" /><path d="M16 8l4 4-4 4M20 12H9" /></>),
    lock: (<><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>),
    send: (<><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4 20-7z" /></>),
    mail: (<><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m2 6 10 7 10-7" /></>),
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function toneOf(score: number | null, verdict: Verdict | null): "good" | "warn" | "bad" | "neutral" {
  if (verdict === "Отлично подходит" || verdict === "Хорошо подходит") return "good"
  if (verdict === "Слабо подходит" || verdict === "Допустимо") return "warn"
  if (verdict === "Не подходит" || verdict === "Не рекомендовано") return "bad"
  if (verdict === "Подходит частично") return "neutral"
  if (score == null) return "neutral"
  return score < 20 ? "bad" : score < 40 ? "warn" : score < 60 ? "neutral" : "good"
}
function ParticleCanvas({ tint = "rgba(214,242,100," }: { tint?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext("2d")
    if (!ctx) return
    let W = 0, H = 0, raf = 0, live = true
    let pts: { x: number; y: number; vx: number; vy: number; bx: number; by: number; r: number }[] = []
    const MESH = 120, PUSH = 180
    const m = { x: -9e4, y: -9e4 }
    function build() {
      const n = Math.round(Math.max(18, Math.min(60, (W * H) / 22000)))
      pts = Array.from({ length: n }, () => { const bx = (Math.random() - 0.5) * 0.16; const by = (Math.random() - 0.5) * 0.16; return { x: Math.random() * W, y: Math.random() * H, vx: bx, vy: by, bx, by, r: Math.random() * 1.5 + 0.7 } })
    }
    function size() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const p = cv!.parentElement
      W = p ? p.clientWidth : window.innerWidth
      H = p ? p.clientHeight : window.innerHeight
      cv!.width = Math.round(W * dpr); cv!.height = Math.round(H * dpr)
      cv!.style.width = W + "px"; cv!.style.height = H + "px"
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0); build()
    }
    const onMove = (e: PointerEvent) => { const r = cv!.getBoundingClientRect(); m.x = e.clientX - r.left; m.y = e.clientY - r.top }
    const onLeave = () => { m.x = -9e4; m.y = -9e4 }
    window.addEventListener("pointermove", onMove, { passive: true })
    window.addEventListener("pointerleave", onLeave)
    function frame() {
      ctx!.clearRect(0, 0, W, H)
      for (const p of pts) {
        const dx = p.x - m.x, dy = p.y - m.y, d2 = dx * dx + dy * dy
        if (d2 < PUSH * PUSH) { const d = Math.sqrt(d2) || 1; const f = 1 - d / PUSH; p.vx += (dx / d) * f * f * 1.4; p.vy += (dy / d) * f * f * 1.4 }
        p.vx += (p.bx - p.vx) * 0.03; p.vy += (p.by - p.vy) * 0.03
        p.x += p.vx; p.y += p.vy
        if (p.x < -30) p.x = W + 30; else if (p.x > W + 30) p.x = -30
        if (p.y < -30) p.y = H + 30; else if (p.y > H + 30) p.y = -30
      }
      ctx!.lineWidth = 0.7
      for (let a = 0; a < pts.length; a++) for (let b = a + 1; b < pts.length; b++) {
        const A = pts[a], B = pts[b], ex = A.x - B.x, ey = A.y - B.y, dd = ex * ex + ey * ey
        if (dd < MESH * MESH) { const k = 1 - Math.sqrt(dd) / MESH; ctx!.strokeStyle = tint + (k * 0.13).toFixed(3) + ")"; ctx!.beginPath(); ctx!.moveTo(A.x, A.y); ctx!.lineTo(B.x, B.y); ctx!.stroke() }
      }
      for (const t of pts) { const near = Math.max(0, 1 - Math.hypot(t.x - m.x, t.y - m.y) / 200); ctx!.fillStyle = tint + (0.3 + near * 0.18).toFixed(3) + ")"; ctx!.beginPath(); ctx!.arc(t.x, t.y, t.r + near * 1.4, 0, 6.283); ctx!.fill() }
      if (live) raf = requestAnimationFrame(frame)
    }
    size(); frame()
    let rt = 0
    const onResize = () => { clearTimeout(rt); rt = window.setTimeout(size, 160) }
    window.addEventListener("resize", onResize)
    const onVis = () => { if (document.hidden) { live = false; cancelAnimationFrame(raf) } else if (!live) { live = true; frame() } }
    document.addEventListener("visibilitychange", onVis)
    return () => { live = false; cancelAnimationFrame(raf); window.removeEventListener("pointermove", onMove); window.removeEventListener("pointerleave", onLeave); window.removeEventListener("resize", onResize); document.removeEventListener("visibilitychange", onVis) }
  }, [tint])
  return <canvas ref={ref} aria-hidden="true" className="particles" />
}

const STATE_LABEL: Record<ProductState, string> = { using: "Сейчас использую", want: "Хочу попробовать", finished: "Закончились" }

function Button({ children, onClick, variant = "primary", icon, small, className = "", disabled }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost"; icon?: IconName; small?: boolean; className?: string; disabled?: boolean
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={`btn btn--${variant} ${small ? "btn--small" : ""} ${className}`}>
      {icon && <Icon name={icon} size={small ? 15 : 17} />}
      {children}
    </button>
  )
}

function VerdictPill({ verdict, score }: { verdict: Verdict | null; score: number | null }) {
  if (verdict == null) return null
  return <span className={`pill pill--${toneOf(score, verdict)}`}>{verdict}</span>
}

function ScoreBadge({ score, verdict, recommendationStatus }: {
  score: number | null;
  verdict?: string | null;
  recommendationStatus?: string | null;
}) {
  const value = score ?? null
  const normalized = normalizeVerdict(verdict)
  const status = normalized || recommendationStatus
  if (value == null) {
    return status ? <span className="score-text">{status}</span> : null
  }
  return (
    <span className="score-badge">
      {Math.round(value)}%{status ? ` · ${status}` : ""}
    </span>
  )
}

function Avatar({ size = 34, initials = skinProfile.initials }: { size?: number; initials?: string }) {
  return <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.4 }}>{initials}</span>
}

function ScoreRing({ score, label = "совместимость" }: { score: number; label?: string }) {
  const tone = toneOf(score, null)
  const [displayScore, setDisplayScore] = useState(0)

  useEffect(() => {
    const target = Math.round(score)

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplayScore(target)
      return
    }

    let frame = 0
    let startTime: number | null = null
    const duration = 1700

    setDisplayScore(0)

    const tick = (now: number) => {
      if (startTime === null) startTime = now
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 4)
      setDisplayScore(Math.round(target * eased))

      if (progress < 1) {
        frame = window.requestAnimationFrame(tick)
      }
    }

    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [score])

  return (
    <div
      className={`compat-gauge compat-gauge--${tone}`}
      role="img"
      aria-label={`${label}: ${Math.round(score)} процентов`}
    >
      <span className="compat-gauge__value">
        {displayScore}<span className="compat-gauge__percent">%</span>
      </span>
      <span className="compat-gauge__label">{label}</span>
    </div>
  )
}

const PRODUCT_IMAGE_FALLBACK = `data:image/svg+xml;utf8,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#f0f0ef"/><path d="M62 126h76l-10 -42H72z" fill="#d5d4ce"/><circle cx="100" cy="72" r="13" fill="#d5d4ce"/><text x="100" y="160" font-family="sans-serif" font-size="11" text-anchor="middle" fill="#9d9b93">нет фото</text></svg>'
)}`

function ProductImage({ src, alt = "", className = "" }: { src: string; alt?: string; className?: string }) {
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    setLoaded(false)
    setFailed(false)
  }, [src])
  return (
    <span className={`pimg ${loaded ? "pimg--loaded" : ""} ${className}`}>
      {!loaded && <span className="pimg__skeleton" aria-hidden="true" />}
      <img
        src={failed || !src ? PRODUCT_IMAGE_FALLBACK : src}
        alt={alt}
        loading="lazy"
        decoding="async"
        className="pimg__img"
        onLoad={() => setLoaded(true)}
        onError={() => { setFailed(true); setLoaded(true) }}
      />
    </span>
  )
}

function ProductCardSkeleton() {
  return (
    <article className="pcard pcard--skeleton" aria-hidden="true">
      <div className="pcard__img"><span className="pcard__skeleton-img" /></div>
      <div className="pcard__body">
        <span className="skeleton-line skeleton-line--short" />
        <span className="skeleton-line" />
        <span className="skeleton-line skeleton-line--tiny" />
      </div>
      <div className="pcard__foot"><span className="skeleton-line skeleton-line--button" /></div>
    </article>
  )
}

function ProductName({ name }: { name: string }) {
  return (
    <div className="pcard__name-wrap">
      <span className="pcard__name">{name}</span>
    </div>
  )
}

function ProductCard({ product, checking = false, onOpen, onRemove, onSelect, selected }: {
  product: Product; checking?: boolean; onOpen?: () => void; onRemove?: () => void; onSelect?: () => void; selected?: boolean
}) {
  const checked = product.match != null
  return (
    <article className={`pcard ${selected ? "pcard--selected" : ""}`}>
      {onRemove && !onSelect && (
        <button type="button" className="pcard__remove" onClick={(e) => { e.stopPropagation(); onRemove() }} aria-label="Убрать с полки"><Icon name="close" size={14} /></button>
      )}
      {onSelect && (
        <button type="button" className={`pcard__select ${selected ? "pcard__select--on" : ""}`} onClick={(e) => { e.stopPropagation(); onSelect() }} aria-label="Выбрать">{selected ? <Icon name="check" size={14} /> : null}</button>
      )}
      <button type="button" className="pcard__main" onClick={onSelect ? onSelect : onOpen} aria-label={product.name}>
        <div className="pcard__img">
          <ProductImage src={product.image} />
          {product.match && <ScoreBadge score={product.match.score} verdict={product.match.verdict} recommendationStatus={product.match.recommendation_status} />}
          {product.verified && <span className="pcard__verified"><Icon name="check" size={11} /> Проверено</span>}
          {product.state && <span className={`pcard__state pcard__state--${product.state}`} />}
        </div>
        <div className="pcard__body">
          <p className="pcard__brand">{product.brand}</p>
          <ProductName name={product.name} />
          <p className="pcard__cat">{product.subcategory ? `${product.category} · ${product.subcategory}` : product.category}</p>
        </div>
      </button>
      <div className="pcard__foot">
        {!checked && (checking ? (
          <span className="pcard__checking"><img src="/loading.gif" alt="" /> Проверяем…</span>
        ) : (
          <button type="button" className="pcard__check" onClick={onOpen}>
            <Icon name="sparkle" size={13} /> Проверить совместимость
          </button>
        ))}
      </div>
    </article>
  )
}

const NAV: { id: Page; icon: IconName; label: string }[] = [
  { id: "home", icon: "home", label: "Главная" },
  { id: "shelf", icon: "shelf", label: "Моя полка" },
  { id: "scan", icon: "scan", label: "Сканировать" },
  { id: "catalog", icon: "search", label: "Каталог" },
  { id: "report", icon: "chart", label: "Отчёт" },
  { id: "profile", icon: "user", label: "Профиль" },
]
const MOBILE_NAV: { id: Page; icon: IconName; label: string }[] = [
  { id: "home", icon: "home", label: "Главная" },
  { id: "shelf", icon: "shelf", label: "Полка" },
  { id: "scan", icon: "scan", label: "Сканировать" },
  { id: "catalog", icon: "search", label: "Каталог" },
  { id: "profile", icon: "user", label: "Профиль" },
]

function Sidebar({ page, onNavigate, user, onAuth, onPricing, onPoints }: {
  page: Page; onNavigate: (p: Page) => void; user: User | null; onAuth: () => void; onPricing: () => void; onPoints: () => void
}) {
  return (
    <aside className="sidebar">
      <div className="brand"><strong>айдерми</strong></div>
      <nav className="nav-list">
        {NAV.map((item) => {
          const locked = item.id === "report"
          return (
            <button key={item.id} type="button" className={`nav-item ${page === item.id ? "nav-item--active" : ""}`} onClick={() => onNavigate(item.id)}>
              <Icon name={item.icon} /> {item.label}
              {locked && <Icon name="lock" size={14} />}
            </button>
          )
        })}
      </nav>
      {user ? (
        <div className="sidebar-card">
          <span className="sidebar-card__icon"><Icon name="credits" /></span>
          <strong>{user.points} баллов</strong>
          <p>Тариф {PLANS.find((p) => p.key === user.plan)?.title} · {PLANS.find((p) => p.key === user.plan)?.monthlyPoints} баллов/мес.</p>
          <button type="button" className="sidebar-card__btn" onClick={onPoints}>Пополнить баллы</button>
          <button type="button" className="sidebar-card__btn sidebar-card__btn--ghost" onClick={onPricing}>Управлять подпиской</button>
        </div>
      ) : (
        <div className="sidebar-card">
          <span className="sidebar-card__icon"><Icon name="sparkle" /></span>
          <strong>Войдите в аккаунт</strong>
          <p>Баллы, полка и отчёты доступны после входа.</p>
          <button type="button" className="sidebar-card__btn" onClick={onAuth}>Войти / регистрация</button>
        </div>
      )}
      <button type="button" className="profile-mini" onClick={() => onNavigate("profile")}>
        <Avatar size={30} initials={user?.initials ?? "Г"} />
        <span><strong>{user?.name ?? "Гость"}</strong><small>{user ? getUserProfile().skinType : "Тип кожи не задан"}</small></span>
        <Icon name="chevron" size={15} />
      </button>
    </aside>
  )
}

function GlobalBar({ query, onQuery, user, onAuth, onPricing, onPoints, onLogout, onNavigate, onOpen, onHelp }: {
  query: string; onQuery: (v: string) => void; user: User | null; onAuth: () => void; onPricing: () => void; onPoints: () => void; onLogout: () => void; onNavigate: (p: Page) => void; onOpen: (p: Product) => void; onHelp: () => void
}) {
  const [focused, setFocused] = useState(false)
  const [matches, setMatches] = useState<Product[]>([])
  useEffect(() => {
    const q = query.trim()
    if (!q) { setMatches([]); return }
    const t = window.setTimeout(async () => {
      try {
        const res = await api.catalog({ search: q, limit: 6 })
        setMatches((res.products || []).map(mapApiProduct).filter((p) => p.name && p.name !== "Продукт"))
      } catch { setMatches([]) }
    }, 250)
    return () => window.clearTimeout(t)
  }, [query])
  return (
    <header className="globalbar">
      <div className="search search--top search--autocomplete">
        <Icon name="search" size={17} />
        <input value={query} onChange={(e) => onQuery(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => window.setTimeout(() => setFocused(false), 150)} placeholder="Название, бренд или актив…" />
        {query && <button type="button" onClick={() => onQuery("")} className="search__clear" aria-label="Очистить"><Icon name="close" size={15} /></button>}
        {focused && query && (
          <div className="autocomplete">
            {matches.map((p) => (
              <button key={p.id} type="button" className="autocomplete__item" onMouseDown={(e) => { e.preventDefault(); onOpen(p); onQuery(""); setFocused(false) }}>
                <img src={p.image} alt="" />
                <span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>
              </button>
            ))}
            <button type="button" className="autocomplete__all" onMouseDown={(e) => { e.preventDefault(); onNavigate("catalog"); setFocused(false) }}>Смотреть все результаты в каталоге →</button>
          </div>
        )}
      </div>
      <div className="globalbar__actions">
        <button type="button" className="icon-btn icon-btn--help" onClick={onHelp} aria-label="Помощь"><span className="help-mark">?</span></button>
        {user ? (
          <>
            <button type="button" className="points-chip" onClick={onPoints}><Icon name="credits" size={16} /><strong>{user.points}</strong><span>баллов · {PLANS.find((p) => p.key === user.plan)?.title}</span></button>
            <button type="button" className="icon-btn" onClick={onLogout} aria-label="Выйти"><Icon name="logout" size={18} /></button>
          </>
        ) : (
          <Button small onClick={onAuth}>Войти</Button>
        )}
      </div>
    </header>
  )
}

function Topbar({ page, onNavigate, onHelp, user, onAuth, onPoints }: {
  page: Page; onNavigate: (p: Page) => void; onHelp: () => void; user: User | null; onAuth: () => void; onPoints: () => void
}) {
  const title = NAV.find((n) => n.id === page)?.label ?? ""
  return (
    <header className="topbar">
      <span className="topbar__brand"><strong>айдерми</strong></span>
      <span className="topbar__title">{title}</span>
      <div className="topbar__actions">
        {user && (
          <button type="button" className="topbar__points" onClick={onPoints} aria-label="Пополнить баллы"><Icon name="credits" size={15} /><strong>{user.points}</strong></button>
        )}
        <button type="button" className="icon-btn icon-btn--help" onClick={onHelp} aria-label="Помощь"><span className="help-mark">?</span></button>
        {user ? (
          <button type="button" className="icon-btn" onClick={() => onNavigate("profile")} aria-label="Профиль"><Avatar size={28} initials={user.initials} /></button>
        ) : (
          <button type="button" className="icon-btn" onClick={onAuth} aria-label="Войти"><Icon name="user" size={19} /></button>
        )}
      </div>
    </header>
  )
}

function BottomNav({ page, onNavigate }: { page: Page; onNavigate: (p: Page) => void }) {
  return (
    <nav className="bottom-nav">
      {MOBILE_NAV.map((item) => {
        const isScan = item.id === "scan"
        const active = page === item.id
        return (
          <button key={item.id} type="button" className={`bottom-nav__item ${isScan ? "bottom-nav__item--scan" : ""} ${active ? "bottom-nav__item--active" : ""}`} onClick={() => onNavigate(item.id)} aria-label={item.label}>
            <span className="bottom-nav__icon"><Icon name={item.icon} size={isScan ? 24 : 21} /></span>
            <span>{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}

function SectionHead({ eyebrow, title, action, actionLabel }: { eyebrow: string; title: string; action?: () => void; actionLabel?: string }) {
  return (
    <div className="section-head">
      <div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>
      {action && actionLabel && <Button variant="ghost" small onClick={action}>{actionLabel} <Icon name="arrow" size={14} /></Button>}
    </div>
  )
}

function PageHeading({ eyebrow, title, lead, action }: { eyebrow: string; title: string; lead?: string; action?: ReactNode }) {
  return (
    <div className="page-head">
      <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{lead && <p className="lead">{lead}</p>}</div>
      {action}
    </div>
  )
}

function Sparkline({ values }: { values: number[] }) {
  const w = 120, h = 40, min = Math.min(...values), max = Math.max(...values)
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * (h - 4) - 2}`).join(" ")
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="sparkline" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function HScroll({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const scroll = (dir: number) => ref.current?.scrollBy({ left: dir * 280, behavior: "smooth" })
  return (
    <div className="hscroll-wrap">
      <button type="button" className="hscroll-arrow hscroll-arrow--prev" onClick={() => scroll(-1)} aria-label="Назад"><Icon name="back" size={17} /></button>
      <div className="hscroll" ref={ref}>{children}</div>
      <button type="button" className="hscroll-arrow hscroll-arrow--next" onClick={() => scroll(1)} aria-label="Вперёд"><Icon name="chevron" size={17} /></button>
    </div>
  )
}
const SWIPE_THRESHOLD = 70

function AutoPickCarousel({
  items,
  onOpen,
  onAdd,
}: {
  items: Product[]
  onOpen: (p: Product, card?: HTMLElement) => void
  onAdd: (p: Product) => Promise<boolean> | boolean | void
}) {
  const [order, setOrder] = useState<number[]>(() =>
    items.map((_, index) => index)
  )

  const [dragX, setDragX] = useState(0)
  const [dragY, setDragY] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [swiping, setSwiping] = useState(false)
  const [returning, setReturning] = useState(false)
  const [swipeDirection, setSwipeDirection] = useState<1 | -1>(1)

  const startX = useRef(0)
  const startY = useRef(0)
  const lastX = useRef(0)
  const lastTime = useRef(0)
  const velocityX = useRef(0)

  const movedRef = useRef(false)
  const pointerIdRef = useRef<number | null>(null)

  // ID конкретной карточки, которая сейчас улетает.
  // Это важно: после paginate её position меняется с 0 на 3.
  const swipingItemRef = useRef<number | null>(null)
  const addingItemRef = useRef<number | null>(null)

  const total = items.length

  useEffect(() => {
    setOrder((current) => {
      const valid = current.filter(
        (index) => index >= 0 && index < items.length
      )

      const missing = items
        .map((_, index) => index)
        .filter((index) => !valid.includes(index))

      return [...valid, ...missing]
    })
  }, [items])

  if (total === 0 || order.length === 0) {
    return (
      <div className="autopick-carousel">
        <p>Вы просмотрели все товары в этой подборке.</p>
      </div>
    )
  }

  const visibleCount = Math.min(order.length, 4)
  const visibleOrder = order.slice(0, visibleCount)
  const currentIndex = order[0] ?? 0

  const removeSwipedCard = (item: number, direction: 1 | -1) => {
    if (swiping) return

    swipingItemRef.current = item
    setSwipeDirection(direction)
    setSwiping(true)
    setReturning(false)
    setDragging(false)

    window.setTimeout(() => {
      setOrder((current) => current.filter((index) => index !== item))
      setDragX(0)
      setDragY(0)
      setReturning(false)
      setSwiping(false)
      swipingItemRef.current = null
      movedRef.current = false
    }, 320)
  }

  const finishSwipe = (direction: 1 | -1) => {
    const item = order[0]
    if (item == null || swiping || addingItemRef.current !== null) return

    const product = items[item]
    if (!product) return

    if (direction === -1) {
      removeSwipedCard(item, direction)
      return
    }

    addingItemRef.current = item
    setDragging(false)

    void Promise.resolve()
      .then(() => onAdd(product))
      .then((success) => {
        if (success) removeSwipedCard(item, direction)
      })
      .catch(() => {
        // При ошибке оставляем карточку в колоде.
      })
      .finally(() => {
        addingItemRef.current = null
      })
  }

  const handlePointerDown = (
    e: ReactPointerEvent<HTMLDivElement>
  ) => {
    if (swiping) return
    if (e.pointerType === "mouse" && e.button !== 0) return

    pointerIdRef.current = e.pointerId

    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {}

    setDragging(true)
    setDragX(0)
    setDragY(0)

    movedRef.current = false

    startX.current = e.clientX
    startY.current = e.clientY

    lastX.current = e.clientX
    lastTime.current = performance.now()

    velocityX.current = 0
  }

  const handlePointerMove = (
    e: ReactPointerEvent<HTMLDivElement>
  ) => {
    if (!dragging || swiping) return

    const now = performance.now()

    const dx = e.clientX - startX.current
    const dy = e.clientY - startY.current

    const dt = Math.max(now - lastTime.current, 1)

    // Та же velocity-механика, что в референсе.
    velocityX.current =
      (e.clientX - lastX.current) / dt * 60

    lastX.current = e.clientX
    lastTime.current = now

    if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
      movedRef.current = true
    }

    // Точный elastic из референса.
    const elastic = 0.7

    setDragX(dx * elastic)
    setDragY(dy * elastic * 0.4)
  }

  const handlePointerUp = (
    e?: ReactPointerEvent<HTMLDivElement>
  ) => {
    if (!dragging || swiping) return

    if (
      e &&
      pointerIdRef.current === e.pointerId
    ) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId)
      } catch {}
    }

    pointerIdRef.current = null
    setDragging(false)

    const rawDx =
      lastX.current - startX.current

    const distance = Math.abs(rawDx)
    const velocity = Math.abs(velocityX.current)

    // Аналог swipePower из референса:
    // abs(offset) * velocity.
    //
    // Оставляем также distance threshold,
    // чтобы медленный нормальный свайп работал.
    const shouldSwipe =
      movedRef.current &&
      order.length > 0 &&
      (
        distance > 90 ||
        distance * velocity > 10000
      )

    if (shouldSwipe) {
      finishSwipe(rawDx > 0 ? 1 : -1)
      return
    }

    setDragX(0)
    setDragY(0)

    window.setTimeout(() => {
      movedRef.current = false
    }, 80)
  }

  return (
    <div
      className={`autopick-carousel ${
        dragging
          ? "autopick-carousel--dragging"
          : ""
      } ${
        swiping
          ? "autopick-carousel--swiping"
          : ""
      }`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      {visibleOrder.map((itemIdx, position) => {
        const product = items[itemIdx]

        if (!product) return null

        const isFront = position === 0

        // После paginate карточка уже position=3.
        // Поэтому определяем её по itemIdx.
        const isSwipingCard =
          swiping &&
          swipingItemRef.current === itemIdx

        const style: CSSProperties = {}

        // ======================================================
        // DRAG
        // ======================================================
        if (isFront && dragging) {
          style.transition = "none"

          style.transform = `
            scale(1)
            translateX(${dragX}px)
            translateY(${dragY}px)
            rotate(${dragX * 0.04}deg)
          `
        }

        // ======================================================
        // ФАЗА 1 + ФАЗА 2
        //
        // Конкретная карточка летит и остаётся в точке
        // ±500px даже после того, как стала position=3.
        // ======================================================
        if (isSwipingCard && !returning) {
          style.transition =
            "transform .3s cubic-bezier(.4, 0, 1, 1)"

          style.transform = `
            scale(.9)
            translateX(${swipeDirection * 500}px)
            translateY(40px)
            rotate(${swipeDirection * 20}deg)
          `

          style.zIndex = 4
        }

        // ======================================================
        // ФАЗА 3
        //
        // Не задаём transform вообще.
        //
        // CSS:
        // data-stack="3"
        //
        // плавно переводит карточку:
        //
        // ±500px → 110px
        // 40px   → 16px
        // ±20deg → 7deg
        // scale .9 → .8
        // ======================================================
        if (isSwipingCard && returning) {
          style.transition =
            "transform .42s cubic-bezier(.16, 1, .3, 1)"
        }

        return (
          <article
            key={product.id}
            className="autopick-carousel__card"
            data-stack={position}
            style={style}
            onClick={(event) => {
              if (
                !movedRef.current &&
                !swiping
              ) {
                onOpen(product, event.currentTarget as HTMLElement)
              }
            }}
          >
            <div className="autopick-carousel__image">
              <div
                className="autopick-carousel__swipe-tint autopick-carousel__swipe-tint--skip"
                style={{ opacity: isFront && dragging && dragX < 0 ? Math.min(0.32, Math.abs(dragX) / 280) : 0 }}
                aria-hidden="true"
              />
              <div
                className="autopick-carousel__swipe-tint autopick-carousel__swipe-tint--add"
                style={{ opacity: isFront && dragging && dragX > 0 ? Math.min(0.32, dragX / 280) : 0 }}
                aria-hidden="true"
              />
              <div
                className="autopick-carousel__swipe-hint autopick-carousel__swipe-hint--skip"
                style={{ opacity: isFront && dragging && dragX < 0 ? Math.min(1, Math.abs(dragX) / 90) : 0 }}
                aria-hidden="true"
              >
                ← Пропускаем
              </div>
              <div
                className="autopick-carousel__swipe-hint autopick-carousel__swipe-hint--add"
                style={{ opacity: isFront && dragging && dragX > 0 ? Math.min(1, dragX / 90) : 0 }}
                aria-hidden="true"
              >
                Добавляем →
              </div>
              <img
                src={product.image}
                alt=""
                loading="lazy"
                draggable={false}
              />

              {product.match && (
                <ScoreBadge
                  score={product.match.score}
                  verdict={product.match.verdict}
                  recommendationStatus={product.match.recommendation_status}
                />
              )}
            </div>

            <div className="autopick-carousel__body">
              <p className="autopick-carousel__brand">
                {product.brand}
              </p>

              <h3>{product.name}</h3>

              <p className="autopick-carousel__category">
                {product.category}
              </p>

              
            </div>
          </article>
        )
      })}

      {total > 1 && (
        <div className="autopick-carousel__counter">
          {total - order.length + 1} / {total}
        </div>
      )}
    </div>
  )
}

function HomePage({ onNavigate, onOpen, onScan, user, items, shelfItems }: {
  onNavigate: (p: Page) => void; onOpen: (p: Product) => void; onScan: () => void; user: User | null; items: Product[]; shelfItems: Product[]
}) {
  const using = items.filter((p) => p.state === "using").slice(0, 4)
  const recent = items.filter((p) => p.match).slice(0, 6)
  // Тот же источник результата, что и «Моя полка» (shelfItems) — без отдельного расчёта для Home.
  const shelfSource = shelfItems.length ? shelfItems : items.filter((p) => p.state)
  const avg = (() => {
    const scored = shelfSource.filter((p) => p.match != null)
    return scored.length ? Math.round(scored.reduce((s, p) => s + (p.match?.score ?? 0), 0) / scored.length) : null
  })()
  // Реальные рекомендации: есть match, не на полке, отсортированы по score.
  // Показываем до 6 карточек (если доступно), без изменения ранжирования.
  const recommended = items.filter((p) => p.match != null && !p.state).sort((a, b) => (b.match?.score ?? 0) - (a.match?.score ?? 0)).slice(0, 3)
  return (
    <div className="page">
      <section className="hero">
        <ParticleCanvas />
        <div className="hero__inner">
          <p className="eyebrow">{user ? `Доброе утро, ${user.name}` : "Добро пожаловать"}</p>
          <h1 className="hero__title">Косметика, которая<br />действительно подходит</h1>
          <p className="hero__lead">айдерми связывает состав с вашей кожей и показывает, что сработает, а что нет.</p>
          <div className="hero__actions">
            <Button icon="camera" onClick={onScan}>Сканировать упаковку</Button>
            <Button variant="secondary" icon="search" onClick={() => onNavigate("catalog")}>Найти в каталоге</Button>
          </div>
        </div>
      </section>

      <div className="grid-2">
        <section className="panel panel--click" onClick={() => onNavigate("shelf")}>
          <p className="eyebrow">Моя полка · сводка</p>
          <div className="report-preview">
            <div className="report-preview__num"><strong>{avg ?? "—"}</strong><span>{avg != null ? "%" : ""}</span></div>
            <p className="report-preview__label">средняя совместимость полки</p>
          </div>
        </section>

        <section className="panel">
          <p className="eyebrow">Профиль кожи</p>
          <h3 className="panel__h3">{getUserProfile().skinType}</h3>
          <div className="chips">
            {getUserProfile().concerns.slice(0, 3).map((g) => <span key={g} className="chip">{g}</span>)}
            {getUserProfile().allergies.slice(0, 2).map((t) => <span key={t} className="chip">{t}</span>)}
            {getUserProfile().concerns.length === 0 && getUserProfile().allergies.length === 0 && <span className="chip">Профиль не заполнен</span>}
          </div>
          <Button variant="ghost" small icon="user" onClick={() => onNavigate("profile")} className="mt">Перепройти опрос</Button>
        </section>
      </div>

      <section className="block">
        <SectionHead eyebrow="Недавно" title="Проверенные продукты" action={() => onNavigate("catalog")} actionLabel="Все" />
        <HScroll>{recent.map((p) => <ProductCard key={p.id} product={p} onOpen={() => onOpen(p)} />)}</HScroll>
      </section>

      <section className="block">
        <SectionHead eyebrow="Моя полка" title="Сейчас использую" action={() => onNavigate("shelf")} actionLabel="Полка" />
        <HScroll>{using.map((p) => <ProductCard key={p.id} product={p} onOpen={() => onOpen(p)} />)}</HScroll>
      </section>

      <section className="block">
        <SectionHead eyebrow="Рекомендации" title="Проверьте ещё" action={() => onNavigate("catalog")} actionLabel="Каталог" />
        <div className="rec-list">
          {recommended.map((p) => (
            <button key={p.id} type="button" className="rec" onClick={() => onOpen(p)}>
              <img src={p.image} alt="" loading="lazy" />
              <span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>
              {p.match && <ScoreBadge score={p.match.score} verdict={p.match.verdict} recommendationStatus={p.match.recommendation_status} />}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
function GuestHomePage({ onAuth, onStart }: { onAuth: () => void; onStart: () => void }) {
  // Гостевая главная: только презентация продукта. Никаких персональных блоков,
  // статистики полки или имитации анализа — все действия ведут к входу/регистрации.
  const steps = [
    {
      n: "01",
      title: "Выберите средство",
      text: "Найдите продукт в каталоге или отсканируйте упаковку — айдерми распознаёт состав с этикетки.",
    },
    {
      n: "02",
      title: "айдерми разбирает состав",
      text: "Ингредиенты сопоставляются с вашим профилем кожи: типом, чувствительностью и целями ухода.",
    },
    {
      n: "03",
      title: "Получите результат",
      text: "Вы увидите оценку совместимости и объяснение факторов, которые её повышают или снижают.",
    },
  ]
  const shots = [
    { key: "scan", label: "Сканирование средства", hint: "Распознавание состава" },
    { key: "result", label: "Результат анализа", hint: "Оценка совместимости" },
    { key: "report", label: "Подробный отчёт", hint: "Факторы и объяснение" },
  ]
  return (
    <div className="guest-page">
      <header className="guest-header">
        <span className="guest-header__brand">айдерми</span>
        <div className="guest-header__actions">
          <button type="button" className="guest-link" onClick={onAuth}>Войти</button>
          <Button small onClick={onStart}>Начать</Button>
        </div>
      </header>

      <section className="guest-hero">
        <ParticleCanvas tint="rgba(214, 242, 100," />
        <div className="guest-hero__inner">
          <h1 className="guest-hero__title">
            айдерми анализирует ингредиенты и честно показывает, насколько средство совместимо с вашей кожей.
          </h1>
          <p className="guest-hero__lead">Без рекламы и догадок — только состав.</p>
          <div className="guest-hero__actions">
            <Button icon="sparkle" onClick={onStart}>Заполнить профиль кожи и проверить средство</Button>
            <Button variant="secondary" onClick={onAuth}>Войти или зарегистрироваться</Button>
          </div>
         </div>
      </section>

      <section className="guest-block">
        <SectionHead eyebrow="Как это работает" title="Три шага до понятного результата" />
        <div className="guest-steps">
          {steps.map((st) => (
            <article className="guest-step" key={st.n}>
              <span className="guest-step__num">{st.n}</span>
              <h3>{st.title}</h3>
              <p>{st.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="guest-block">
        <SectionHead eyebrow="Скриншоты" title="Как выглядит айдерми" />
        <div className="phone-row">
          {shots.map((shot) => (
            <figure className="phone-mock" key={shot.key}>
              <div className="phone-mock__frame">
                <div className="phone-mock__screen" data-screenshot-slot={shot.key}>
                  {/* Слот под будущий скриншот: замените содержимое на <img className="phone-mock__img" src="…" alt="…" /> */}
                  <span className="phone-mock__tag">Скриншот</span>
                  <strong>{shot.label}</strong>
                  <small>{shot.hint}</small>
                </div>
              </div>
              <figcaption>{shot.label}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="guest-cta">
        <h2>Начните с одного средства</h2>
        <p>
          Добавьте продукт, посмотрите оценку совместимости и разберитесь, какие ингредиенты работают на вашу кожу.
        </p>
        <div className="guest-cta__actions">
          <Button icon="sparkle" onClick={onStart}>Заполнить профиль кожи и проверить средство</Button>
          <button type="button" className="guest-link" onClick={onAuth}>У меня уже есть аккаунт</button>
        </div>
      </section>
    </div>
  )
}

function GuestQuizScreen({ onDone, onBack }: {
  onDone: (p: { skinType: string; age?: string; concerns?: string[]; allergies?: string[]; structured?: Record<string, unknown> }) => void
  onBack: () => void
}) {
  return (
    <div className="page guest-flow">
      <div className="guest-flow__head">
        <button type="button" className="guest-link" onClick={onBack}>← На главную</button>
        <p className="eyebrow">Гостевая проверка · шаг 1 из 3</p>
        <h1 className="guest-flow__title">Профиль кожи</h1>
        <p className="guest-flow__lead">Ответьте на вопросы — по профилю айдерми рассчитает совместимость выбранного средства.</p>
      </div>
      <Questionnaire onDone={onDone} />
    </div>
  )
}

function GuestSelectScreen({ onPick, onScan, busy, error }: {
  onPick: (p: ApiProduct) => void
  onScan: () => void
  busy: boolean
  error: string
}) {
  const [q, setQ] = useState("")
  const [results, setResults] = useState<ApiProduct[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState("")

  useEffect(() => {
    const query = q.trim()
    if (query.length < 2) { setResults([]); setSearching(false); return }
    let alive = true
    const t = window.setTimeout(async () => {
      setSearching(true)
      try {
        const res = await api.catalog({ search: query, limit: 8 })
        if (!alive) return
        setResults(((res.products || []) as ApiProduct[]).filter((p) => p.name && p.name !== "Продукт"))
        setSearchError("")
      } catch {
        if (!alive) return
        setResults([])
        setSearchError("Не удалось выполнить поиск. Попробуйте ещё раз.")
      } finally {
        if (alive) setSearching(false)
      }
    }, 300)
    return () => { alive = false; window.clearTimeout(t) }
  }, [q])

  return (
    <div className="page guest-flow">
      <div className="guest-flow__head">
        <p className="eyebrow">Гостевая проверка · шаг 2 из 3</p>
        <h1 className="guest-flow__title">Выберите одно средство</h1>
        <p className="guest-flow__lead">
          Без регистрации доступна одна проверка одного средства. Найдите продукт в каталоге или отсканируйте упаковку.
        </p>
      </div>

      <section className="panel guest-select">
        <label className="guest-search">
          <Icon name="search" size={17} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Название или бренд" />
          {q && <button type="button" onClick={() => setQ("")} aria-label="Очистить"><Icon name="close" size={15} /></button>}
        </label>

        {searching && <p className="panel__note">Ищем…</p>}
        {searchError && <p className="guest-flow__error" role="alert">{searchError}</p>}
        {!searching && q.trim().length >= 2 && results.length === 0 && !searchError && (
          <p className="panel__note">Ничего не нашлось. Попробуйте другое название или отсканируйте упаковку.</p>
        )}

        <div className="guest-select__list">
          {results.map((item) => (
            <button
              key={`${item.id}-${item.slug}`}
              type="button"
              className="guest-select__item"
              onClick={() => onPick(item)}
              disabled={busy}
            >
              <img src={mapApiProduct(item).image} alt="" />
              <span>
                <strong>{item.name}</strong>
                <small>{[item.brand, item.catalog_category].filter(Boolean).join(" · ")}</small>
              </span>
              <Icon name="arrow" size={15} />
            </button>
          ))}
        </div>

        <div className="guest-select__scan">
          <Button variant="secondary" icon="camera" onClick={onScan} disabled={busy}>Сканировать упаковку</Button>
          <span className="panel__note">Можно сфотографировать упаковку или ввести состав вручную.</span>
        </div>

        {busy && <p className="guest-flow__busy"><span className="spin" /> Считаем совместимость…</p>}
        {error && <p className="guest-flow__error" role="alert">{error}</p>}
      </section>
    </div>
  )
}

function GuestResultScreen({ product, guestToken, onSignup, onLogin, onRestart }: {
  product: Product
  guestToken: string
  onSignup: () => void
  onLogin: () => void
  onRestart: () => void
}) {
  const [report, setReport] = useState<ReportResult | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState("")

  const score = product.match?.score ?? null
  const recStatus = product.match?.recommendation_status

  const openReport = async () => {
    if (report) { setReport(null); return }
    setReportLoading(true)
    setReportError("")
    try {
      setReport(await api.guestReport(guestToken))
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 0
      setReportError(
        status === 401 || status === 410
          ? "Гостевой сеанс завершён. Начните проверку заново."
          : status === 409
            ? "Для этого средства недостаточно данных для отчёта."
            : "Не удалось сформировать отчёт. Попробуйте ещё раз.",
      )
    } finally {
      setReportLoading(false)
    }
  }

  return (
    <div className="page guest-flow guest-result">
      <div className="guest-flow__head">
        <p className="eyebrow">Гостевая проверка · шаг 3 из 3</p>
        <h1 className="guest-flow__title">Результат проверки</h1>
        <p className="guest-flow__lead">{[product.brand, product.name].filter(Boolean).join(" · ")}</p>
      </div>

      <section className="panel guest-result__summary">
        {score != null ? (
          <div className="guest-result__score">
            <ScoreRing score={score} label={recStatus === "Не рекомендовано" ? "негативная оценка" : "совместимость"} />
            <div>
              <p className="guest-result__verdict">{product.match?.verdict || recStatus || "Проверка завершена"}</p>
              {product.match?.summary && <p className="guest-result__text">{product.match.summary}</p>}
              {recStatus && <p className="panel__note">{recStatus}</p>}
            </div>
          </div>
        ) : (
          <div>
            <h3 className="panel__h3">Недостаточно данных</h3>
            <p className="panel__note">
              {product.match?.verdict || "Не удалось корректно оценить совместимость: для этого средства не хватает достоверного состава."}
            </p>
          </div>
        )}

        {(product.match?.safe_ingredients?.length || product.match?.caution_ingredients?.length) ? (
          <div className="guest-result__ings">
            {product.match?.safe_ingredients?.length ? (
              <div>
                <p className="eyebrow">Безопасные ингредиенты</p>
                <div className="chips">{product.match.safe_ingredients.slice(0, 8).map((i) => <span key={i} className="chip">{i}</span>)}</div>
              </div>
            ) : null}
            {product.match?.caution_ingredients?.length ? (
              <div>
                <p className="eyebrow">Требуют внимания</p>
                <div className="chips">{product.match.caution_ingredients.slice(0, 8).map((i) => <span key={i} className="chip">{i}</span>)}</div>
              </div>
            ) : null}
          </div>
        ) : null}

        {score != null && (
          <div className="guest-result__report-actions">
            <Button icon="file" onClick={openReport} disabled={reportLoading}>
              {reportLoading ? "Готовим отчёт…" : report ? "Скрыть отчёт" : "Открыть полный отчёт"}
            </Button>
            {reportError && <p className="guest-flow__error" role="alert">{reportError}</p>}
          </div>
        )}

        {report && (
          <div className="guest-report" aria-live="polite">
            <h3 className="panel__h3">Подробный отчёт</h3>
            {report.review?.length
              ? report.review.map((f, i) => <p key={i} className="guest-report__frag">{f.text}</p>)
              : null}
            {report.expectations?.normal && <p className="guest-report__frag">{report.expectations.normal}</p>}
            {report.details && <ReportDetails details={report.details} />}
          </div>
        )}
      </section>

      <section className="guest-save">
        <h2>Зарегистрироваться и сохранить результат</h2>
        <p>Аккаунт сохранит эту проверку и откроет полку, историю и повторные проверки без ограничений.</p>
        <div className="guest-save__actions">
          <Button icon="user" onClick={onSignup}>Зарегистрироваться и сохранить результат</Button>
          <button type="button" className="guest-link" onClick={onLogin}>Уже есть аккаунт? Войти</button>
        </div>
        <p className="panel__note">Результат не сохраняется автоматически и исчезнет после перезагрузки страницы.</p>
        <button type="button" className="guest-link guest-save__restart" onClick={onRestart}>Начать заново</button>
      </section>
    </div>
  )
}

function ShelfPage({ items, checkingIds, loading = false, limit = 5, onOpen, onAdd, onRemove, onClear, onDeleteBatch, onRefresh, onBalance }: {
  items: Product[]; checkingIds: Set<number>; loading?: boolean; limit?: number; onOpen: (p: Product) => void; onAdd: () => void; onRemove: (p: Product) => void; onClear: (cabinet: CabinetKey) => void; onDeleteBatch: (ids: number[]) => void; onRefresh?: () => void; onBalance?: (balance: number) => void
}) {
  const [active, setActive] = useState<CabinetKey>("face")
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const wrapRef = useRef<HTMLDivElement>(null)
  const [refreshQuote, setRefreshQuote] = useState<null | { count: number; cost: number; balance: number; remaining: number }>(null)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [refreshMessage, setRefreshMessage] = useState("")
  const [view, setView] = useState<"list" | "rack">("list")
  const [cardsPerShelf, setCardsPerShelf] = useState(5)

  const toggleSelect = (shelfId: number) => {
    setSelected((prev) => { const n = new Set(prev); if (n.has(shelfId)) n.delete(shelfId); else n.add(shelfId); return n })
  }

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const CARD_W = 150, GAP = 12
    const measure = () => {
      if (window.innerWidth <= 760) { setCardsPerShelf(2); return }
      const available = Math.max(CARD_W, el.clientWidth - 8)
      setCardsPerShelf(Math.max(1, Math.floor((available + GAP) / (CARD_W + GAP))))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [active, view])

  useEffect(() => {
    let alive = true
    if (loading || !items.some((item) => item.needs_recheck)) {
      setRefreshQuote(null)
      return () => { alive = false }
    }
    void api.shelfRefreshPreview()
      .then((quote) => {
        if (!alive) return
        setRefreshQuote(quote.count > 0 ? quote : null)
      })
      .catch(() => { if (alive) setRefreshQuote(null) })
    return () => { alive = false }
  }, [items, loading])

  const handleRefresh = async () => {
    if (!refreshQuote || refreshBusy) return
    setRefreshBusy(true)
    setRefreshMessage("")
    const ids = items.filter((item) => item.needs_recheck).map((item) => item.id)
    try {
      const result = await api.shelfRefresh({
        product_ids: ids,
        quoted_cost: refreshQuote.cost,
        // Let the server derive the idempotency key from the same stale set.
        // A double click must not create a second charge.
      })
      setRefreshMessage(
        result.failed.length > 0
          ? `Обновлено ${result.updated} из ${result.updated + result.failed.length}. Не удалось обновить ${result.failed.length}.`
          : `Полка обновлена: ${result.updated} продуктов, списано ${result.charged} баллов.`
      )
      setRefreshQuote(null)
      if (typeof result.balance === "number") onBalance?.(result.balance)
      onRefresh?.()
    } catch (error) {
      setRefreshMessage(error instanceof Error ? error.message : "Не удалось обновить полку.")
    } finally {
      setRefreshBusy(false)
    }
  }

  const cabinet = CABINETS.find((c) => c.key === active) ?? CABINETS[0]
  const shelved = items.filter((p) => p.state && p.cabinet === active)
  const totalShelved = items.filter((p) => p.state).length

  const cells = useMemo(() => {
    const out: { product: Product; cat: string }[] = []
    const cats = Array.from(new Set(shelved.map((p) => p.category)))
    for (const cat of cats) {
      for (const p of shelved) if (p.category === cat) out.push({ product: p, cat })
    }
    return out
  }, [shelved])

  const shelves = useMemo(() => {
    const out: typeof cells[] = []
    for (let i = 0; i < cells.length; i += cardsPerShelf) out.push(cells.slice(i, i + cardsPerShelf))
    if (out.length === 0) out.push([])
    else if (out[out.length - 1].length >= cardsPerShelf) out.push([])
    return out
  }, [cells, cardsPerShelf])

  const groupedShelves = useMemo(() => {
    return shelves.map((shelf) => {
      const groups: { cat: string; cells: typeof shelf }[] = []
      for (const cell of shelf) {
        const last = groups[groups.length - 1]
        if (last && last.cat === cell.cat) last.cells.push(cell)
        else groups.push({ cat: cell.cat, cells: [cell] })
      }
      return groups
    })
  }, [shelves])

  const avg = (() => {
    const scored = shelved.filter((p) => p.match != null)
    return scored.length ? Math.round(scored.reduce((s, p) => s + (p.match?.score ?? 0), 0) / scored.length) : null
  })()
  const shelfVerdict = avg == null ? "—" : avg >= 80 ? "Отлично" : avg >= 60 ? "Нормально" : "Есть конфликты"

  return (
    <div className="page">
      <PageHeading eyebrow="Уход" title="Моя полка" lead="Здесь хранятся ваши средства: видна их совместимость с профилем кожи. Можно отслеживать то, что используете, проверять средства повторно, а система учитывает полку при рекомендациях."
        action={<div className="page-head__actions">
          {selectMode ? (
            <>
              <Button variant="ghost" onClick={() => { onDeleteBatch(Array.from(selected)); setSelectMode(false); setSelected(new Set()) }} disabled={selected.size === 0}>Удалить выбранные ({selected.size})</Button>
              <Button variant="ghost" onClick={() => { setSelectMode(false); setSelected(new Set()) }}>Готово</Button>
            </>
          ) : (
            <>
              <Button icon="plus" onClick={onAdd}>Добавить средство</Button>
              {shelved.length > 0 && <Button variant="ghost" onClick={() => setView((v) => v === "list" ? "rack" : "list")}>{view === "list" ? "Полка" : "Список"}</Button>}
              {shelved.length > 0 && <Button variant="ghost" onClick={() => setSelectMode(true)}>Выбрать</Button>}
              {shelved.length > 0 && <Button variant="ghost" onClick={() => onClear(active)}>Очистить полку</Button>}
            </>
          )}
        </div>} />

      <div className="cabinet-tabs">
        {CABINETS.filter((c) => c.key === "face" || c.key === "makeup").map((c) => {
          const count = items.filter((p) => p.state && p.cabinet === c.key).length
          return (
            <button key={c.key} type="button" className={`cabinet-tab ${active === c.key ? "cabinet-tab--active" : ""}`} onClick={() => setActive(c.key)}>
              {c.short}<span>{count}</span>
            </button>
          )
        })}
      </div>

      {refreshQuote && (
        <div className="shelf-refresh" role="status">
          <div>
            <strong>Есть устаревшие результаты</strong>
            <span>
              Обновить {refreshQuote.count} {refreshQuote.count === 1 ? "продукт" : "продуктов"}?
              Стоимость — {refreshQuote.cost} баллов, останется {refreshQuote.remaining}.
            </span>
          </div>
          <Button variant="secondary" small onClick={() => void handleRefresh()} disabled={refreshBusy}>
            {refreshBusy ? "Обновляем…" : `Обновить за ${refreshQuote.cost}`}
          </Button>
        </div>
      )}
      {refreshMessage && <p className="shelf-refresh__message" role="status">{refreshMessage}</p>}

      <div key={active} className="shelf-anim">
        <div className="shelf-summary">
          <div><strong>{totalShelved}</strong><span>из {limit} средств на полке</span></div>
          <div><strong>{avg != null ? `${avg}%` : "—"}</strong><span>средняя совместимость</span></div>
          <div><strong>{shelfVerdict}</strong><span>как сочетаются средства</span></div>
        </div>

        {view === "list" ? (
          <div className="shelf-list">
            {shelved.map((p) => (
              <div className="shelf-list__row" key={p.id}>
                {selectMode && (
                  <button
                    type="button"
                    className={`shelf-list__select ${selected.has(p.shelf_id ?? p.id) ? "is-selected" : ""}`}
                    aria-label={selected.has(p.shelf_id ?? p.id) ? "Снять выбор" : "Выбрать продукт"}
                    onClick={() => toggleSelect(p.shelf_id ?? p.id)}
                  >
                    {selected.has(p.shelf_id ?? p.id) ? "✓" : ""}
                  </button>
                )}
                <button type="button" className="shelf-list__main" onClick={() => onOpen(p)}>
                  <span className="shelf-list__name">
                    <strong>{p.name}</strong>
                    <small>{p.brand || p.category || "Уход"}</small>
                  </span>
                  <span className="shelf-list__meta">
                    {p.category && <em>{p.category}</em>}
                    <span>{STATE_LABEL[p.state ?? "using"]}</span>
                  </span>
                  <span className={`shelf-list__score ${p.match?.score == null ? "is-empty" : ""}`}>
                    {checkingIds.has(p.id) ? "…" : p.match?.score != null ? `${p.match.score}%` : "—"}
                  </span>
                </button>
                {!selectMode && (
                  <button type="button" className="shelf-list__remove" onClick={() => onRemove(p)} aria-label={`Убрать ${p.name} с полки`}>×</button>
                )}
              </div>
            ))}
            {shelved.length === 0 && (
              loading
                ? <p className="empty"><span className="spin" /> Загружаем полку…</p>
                : <p className="empty">Полка пуста. Добавьте первое средство.</p>
            )}
          </div>
        ) : (
        <div className="shelf-rack-wrap" ref={wrapRef}>
          {groupedShelves.map((shelf, si) => (
            <div className="shelf" key={si}>
              <div className="shelf__row">
                {shelf.map((group, gi) => (
                  <div className="shelf__group" key={gi}>
                    <span className="shelf__group-label">{group.cat}</span>
                    <div className="shelf__group-cards">
                      {group.cells.map((c) => selectMode
                        ? <ProductCard key={c.product.id} product={c.product} onSelect={() => toggleSelect(c.product.shelf_id ?? c.product.id)} selected={selected.has(c.product.shelf_id ?? c.product.id)} />
                        : <ProductCard key={c.product.id} product={c.product} checking={checkingIds.has(c.product.id)} onOpen={() => onOpen(c.product)} onRemove={() => onRemove(c.product)} />)}
                    </div>
                  </div>
                ))}
                {si === groupedShelves.length - 1 && (
                  <button type="button" className="shelf-add" onClick={onAdd} aria-label="Добавить продукт"><Icon name="plus" size={26} /></button>
                )}
              </div>
              <div className="shelf-plank" />
            </div>
          ))}
          {shelved.length === 0 && (
            loading
              ? <p className="empty"><span className="spin" /> Загружаем полку…</p>
              : <p className="empty">Полка пуста. Добавьте первое средство.</p>
          )}
        </div>
        )}
      </div>
      <button type="button" className="shelf-fab" onClick={onAdd} aria-label="Добавить продукт"><Icon name="plus" size={24} /></button>
    </div>
  )
}
function CatalogPage({ items, checkingIds, onOpen, query, onQuery, initialCategory = "", loading = false }: {
  items: Product[]; checkingIds: Set<number>; onOpen: (p: Product) => void; query: string; onQuery: (v: string) => void
  initialCategory?: string; loading?: boolean
}) {
  const [cat, setCat] = useState<string>("Все")
  const [subcat, setSubcat] = useState<string>("Все")
  const [search, setSearch] = useState(query)
  const [results, setResults] = useState<Product[] | null>(null)
  const [fetched, setFetched] = useState<Product[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => { setSearch(query) }, [query])
  useEffect(() => {
    if (!initialCategory) return
    const tax = FACE_TAXONOMY.find((item) => item.title === initialCategory)
    if (tax) {
      setCat(tax.title)
      setSubcat("Все")
      return
    }
    const parent = FACE_TAXONOMY.find((item) => item.subcategories.includes(initialCategory))
    if (parent) {
      setCat(parent.title)
      setSubcat(initialCategory)
    }
  }, [initialCategory])
  useEffect(() => {
    const q = search.trim()
    if (!q) { setResults(null); setSearching(false); return }
    setSearching(true)
    const t = window.setTimeout(async () => {
      try {
        const res = await api.catalog({ search: q, limit: 200 })
        setResults((res.products || []).map(mapApiProduct).filter((p) => p.name && p.name !== "Продукт"))
      } catch { setResults([]) }
      setSearching(false)
    }, 250)
    return () => window.clearTimeout(t)
  }, [search])
  useEffect(() => {
    if (cat === "Все") { setFetched(null); return }
    let cancelled = false
    api.catalog({ catalog_category: cat, limit: 1000, sort: "popular" })
      .then((res) => { if (!cancelled) setFetched((res.products || []).map(mapApiProduct).filter((p) => p.name && p.name !== "Продукт")) })
      .catch(() => { if (!cancelled) setFetched([]) })
    return () => { cancelled = true }
  }, [cat])
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 400)
    window.addEventListener("scroll", onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener("scroll", onScroll)
  }, [])
  const activeTax = FACE_TAXONOMY.find((c) => c.title === cat) ?? null
  const subcats = activeTax ? ["Все", ...activeTax.subcategories] : ["Все"]
  const list = useMemo(() => {
    const base = fetched ?? results ?? items
    const needle = search.trim().toLowerCase()
    return base.filter((p) => {
      if (cat !== "Все" && p.category !== cat) return false
      if (subcat !== "Все" && p.subcategory !== subcat) return false
      if (!needle || results != null) return true
      return [p.name, p.brand, p.category, p.subcategory, ...p.tags].join(" ").toLowerCase().includes(needle)
    })
  }, [fetched, items, results, search, cat, subcat])

  return (
    <div className="page">
      <PageHeading eyebrow="База продуктов" title="Каталог" lead="Проверяйте составы и находите продукты под особенности вашей кожи." />
      <div className="search">
        <Icon name="search" size={18} />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Название, бренд или актив…" />
        {search && <button type="button" onClick={() => setSearch("")} className="search__clear" aria-label="Очистить"><Icon name="close" size={15} /></button>}
      </div>
      <div className="tabs">
        <button type="button" className={`tab ${cat === "Все" ? "tab--active" : ""}`} onClick={() => { setCat("Все"); setSubcat("Все") }}>Все</button>
        {FACE_TAXONOMY.map((c) => (
          <button key={c.key} type="button" className={`tab ${cat === c.title ? "tab--active" : ""}`} onClick={() => { setCat(c.title); setSubcat("Все") }}>{c.title}</button>
        ))}
      </div>
      {activeTax && (
        <div className="tabs tabs--cats">
          {subcats.map((sc) => (
            <button key={sc} type="button" className={`tab ${subcat === sc ? "tab--active" : ""}`} onClick={() => setSubcat(sc)}>{sc}</button>
          ))}
        </div>
      )}
      <div className="product-grid">
        {loading && list.length === 0
          ? Array.from({ length: 6 }, (_, index) => <ProductCardSkeleton key={`skeleton-${index}`} />)
          : list.map((p) => (
            <ProductCard key={p.id} product={p} checking={checkingIds.has(p.id)} onOpen={() => onOpen(p)} />
          ))}
      </div>
      {loading && list.length === 0
        ? <p className="empty">Загружаем каталог…</p>
        : searching
          ? <p className="empty">Ищем…</p>
          : list.length === 0 && <p className="empty">Ничего не нашлось. Попробуйте другой запрос.</p>}
      {scrolled && (
        <button type="button" className="to-top" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} aria-label="Наверх"><Icon name="chevron" size={18} /></button>
      )}
    </div>
  )
}

type ScanMethod = "photo" | "inci" | "link" | "manual"

function extractUrl(raw: string): string {
  const text = (raw || "").trim()
  if (!text) return ""
  const http = text.match(/https?:\/\/[^\s<>"']+/i)
  if (http) return http[0].replace(/[)\].,;:!]+$/, "")
  const www = text.match(/www\.[^\s<>"']+/i)
  if (www) return `https://${www[0].replace(/[)\].,;:!]+$/, "")}`
  return text
}

function highlightInci(raw: string, caution: string[]): React.ReactNode {
  if (!raw) return null
  const bad = (caution || []).map((c) => c.toLowerCase().trim()).filter((c) => c.length >= 4)
  if (!bad.length) return raw
  return raw.split(/(,\s*)/).map((chunk, i) => {
    const key = chunk.toLowerCase()
    return bad.some((c) => key.includes(c))
      ? <span key={i} className="inci__bad">{chunk}</span>
      : chunk
  })
}

function ScanPage({ onContinue, initialMethod, guestToken }: { onContinue: (p: Product) => void; initialMethod?: ScanMethod; guestToken?: string }) {
  const [method, setMethod] = useState<ScanMethod>(initialMethod ?? "photo")
  const [phase, setPhase] = useState<"input" | "recognizing" | "ready">("input")
  const [picked, setPicked] = useState(false)
  const [brand, setBrand] = useState("")
  const [name, setName] = useState("")
  const [inci, setInci] = useState("")
  const [url, setUrl] = useState("")
  const [photoAdded, setPhotoAdded] = useState(false)
  const [inciPhotoAdded, setInciPhotoAdded] = useState(false)
  // Фото продукта при ручном добавлении (необязательное).
  const [manualImage, setManualImage] = useState("")
  const [manualImageBusy, setManualImageBusy] = useState(false)
  const [manualImageError, setManualImageError] = useState("")
  const manualImageRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<Product | null>(null)
  const [slug, setSlug] = useState<string | undefined>(undefined)
  const [imageUrl, setImageUrl] = useState("")
  const [busy, setBusy] = useState(false)
  const [scanError, setScanError] = useState("")

  const METHODS: { id: ScanMethod; title: string; desc: string; icon: IconName }[] = [
    { id: "photo", title: "Скан по фото", desc: "Лицевая и задняя стороны упаковки", icon: "camera" },
    { id: "link", title: "Вставить ссылку", desc: "Вставить ссылку на продукт", icon: "link" },
    { id: "manual", title: "Ручной ввод", desc: "Название, бренд и состав вручную", icon: "pencil" },
  ]

  const needManualFields = method === "inci" || method === "manual"
  const canRun = busy ? false : method === "photo" ? photoAdded : method === "inci" ? brand.trim().length > 0 && name.trim().length > 0 && inciPhotoAdded : method === "link" ? url.trim().length > 0 : brand.trim().length > 0 && name.trim().length > 0 && inci.trim().length > 0

  const buildResult = (b: string, n: string, image: string, productSlug: string | undefined, inci: string, res: { score?: number | null; verdict?: string; analysis_id?: number; recommendation_status?: string; negative_only_score?: number; } | undefined, productId?: number): Product => {
    const score = res?.score ?? null
    const recStatus = res?.recommendation_status
    const negOnly = res && typeof res.negative_only_score === "number" ? res.negative_only_score : null
    const verdict = recStatus === "Не рекомендовано" ? ("Не рекомендовано" as Verdict) : mapVerdict(score, res?.verdict)
    const displayScore = recStatus === "Не рекомендовано" && negOnly != null ? negOnly : score
    const aid = res && typeof res.analysis_id === "number" ? res.analysis_id : undefined
    return {
      id: productId ?? 900 + Math.floor(Math.random() * 90),
      brand: b || "Продукт",
      name: n || "Продукт",
      cabinet: "face",
      category: "Специальный уход",
      image: image || products[6].image,
      tags: [],
      state: "want",
      slug: productSlug,
      ingredients: inci || undefined,
      match: score != null ? { score, verdict: verdict ?? undefined, analysis_id: aid, recommendation_status: recStatus } : undefined,
    }
  }

  const run = async () => {
    if (!canRun) return
    setPhase("recognizing")
    setScanError("")
    const skinType = getUserProfile().skinType
    const profile = buildProfile()
    try {
      if (method === "link") {
        const res = await api.importUrl(extractUrl(url))
        const prod = res.product || {}
        const b = prod.brand || brand.trim()
        const n = prod.name || name.trim()
        setBrand(b); setName(n); setInci(prod.ingredients_raw || "")
        let checkRes
        if (prod.ingredients_raw) {
          checkRes = await api.checkWithIngredients({ product_name: n, skin_type: skinType, profile, ingredients: prod.ingredients_raw, guest_token: guestToken })
        } else {
          checkRes = await api.check({ product_name: n, skin_type: skinType, profile, guest_token: guestToken })
        }
        setResult(buildResult(b, n, prod.image_url || "", prod.slug, prod.ingredients_raw || "", checkRes as { score?: number | null; verdict?: string; analysis_id?: number }, typeof prod.id === "number" ? prod.id : undefined))
      } else if (method === "photo") {
        const checkRes = await api.check({ product_name: name.trim(), skin_type: skinType, profile, guest_token: guestToken })
        setResult(buildResult(brand.trim(), name.trim(), imageUrl || checkRes.image_url || "", slug || checkRes.slug, "", checkRes as { score?: number | null; verdict?: string; analysis_id?: number }))
      } else {
        // inci / manual — анализируем распознанный/введённый состав; если состава
        // нет (не распознался) — проверяем по названию (бэкенд возьмёт INCI из БД).
        let checkRes
        if (inci.trim()) {
          checkRes = await api.checkWithIngredients({ product_name: name.trim(), brand: brand.trim(), skin_type: skinType, profile, ingredients: inci, image_url: manualImage || undefined, guest_token: guestToken })
        } else {
          checkRes = await api.check({ product_name: name.trim(), skin_type: skinType, profile, image_url: manualImage || undefined, guest_token: guestToken })
        }
        setResult(buildResult(brand.trim(), name.trim(), manualImage || "", checkRes.slug || "", inci.trim(), checkRes as { score?: number | null; verdict?: string; analysis_id?: number }))
      }
      setPhase("ready")
    } catch (e) {
      // Не выдаём вымышленный продукт и score. Сохраняем введённые данные/фото,
      // показываем понятную ошибку и оставляем возможность повторить.
      setScanError(
        e instanceof Error && e.message
          ? e.message
          : "Не удалось проверить продукт. Попробуйте ещё раз или загрузите фото состава."
      )
      setPhase("input")
    }
  }

  const fileRef = useRef<HTMLInputElement>(null)

  const uploadManualImage = async (file: File) => {
    setManualImageError("")
    if (!/^image\/(jpeg|png|webp)$/i.test(file.type)) {
      setManualImageError("Поддерживаются JPEG, PNG или WebP.")
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      setManualImageError("Файл больше 8 МБ.")
      return
    }
    setManualImageBusy(true)
    try {
      const res = await api.uploadProductImage(file)
      setManualImage(res.url)
    } catch (e) {
      setManualImageError(e instanceof Error ? e.message : "Не удалось загрузить фото.")
    } finally {
      setManualImageBusy(false)
    }
  }
  const readFileAsDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error("read error"))
    reader.readAsDataURL(file)
  })
  const pickPhoto = () => fileRef.current?.click()

  const takePhoto = async (file: File) => {
    setPhotoAdded(true)
    setBusy(true)
    try {
      const dataUrl = await readFileAsDataUrl(file)
      const res = (await api.identify({ images: [dataUrl] })) as { identified?: { brand?: string; product_name?: string; name?: string }; product?: { name?: string; brand?: string; slug?: string; image_url?: string } }
      const ident = res.identified || {}
      setBrand(ident.brand || res.product?.brand || "COSRX")
      setName(ident.product_name || ident.name || res.product?.name || "Advanced Snail 96 Mucin Power Essence")
      if (res.product?.slug) setSlug(res.product.slug)
      if (res.product?.image_url) setImageUrl(res.product.image_url)
    } catch {
      setBrand("COSRX")
      setName("Advanced Snail 96 Mucin Power Essence")
    } finally {
      setBusy(false)
    }
  }

  const takeInciPhoto = async (file: File) => {
    setInciPhotoAdded(true)
    setBusy(true)
    try {
      const dataUrl = await readFileAsDataUrl(file)
      const res = (await api.compositionRecognize({ images: [dataUrl] })) as { normalized_ingredients?: string[] }
      const ingr = res.normalized_ingredients || []
      setInci(ingr.length ? ingr.join(", ") : "")
    } catch {
      setInci("")
    } finally {
      setBusy(false)
    }
  }

  if (method === "photo" && picked) {
    return (
      <div className="page">
        <PageHeading eyebrow="Проверка" title="Скан по фото" lead="Загрузите лицевую и заднюю стороны одного продукта — этого достаточно для карточки и проверки." />
        <section className="panel scan-form">
          <button type="button" className="scan-back" onClick={() => setPicked(false)}><Icon name="back" size={16} /> Выбрать способ</button>
          <PhotoScan guestToken={guestToken} onContinue={onContinue} />
        </section>
      </div>
    )
  }

  return (
    <div className="page">
      <PageHeading eyebrow="Проверка" title="Сканировать продукт" lead="Выберите способ. Название и бренд обязательны — без них не определить продукт." />
      {phase === "input" && !picked && (
        <div className="scan-methods">
          {METHODS.map((m) => (
            <button key={m.id} type="button" className={`scan-method ${method === m.id ? "scan-method--active" : ""}`} onClick={() => { setMethod(m.id); setPicked(true) }}>
              <span className="scan-method__icon"><Icon name={m.icon} size={20} /></span>
              <strong>{m.title}</strong>
              <small>{m.desc}</small>
            </button>
          ))}
        </div>
      )}

      {phase === "input" && picked && (
        <section className="panel scan-form">
          <button type="button" className="scan-back" onClick={() => setPicked(false)}><Icon name="back" size={16} /> Выбрать способ</button>
          {scanError && <p className="scan-error" role="alert">{scanError}</p>}
          {needManualFields && (
            <div className="scan-form__row">
              <label><span>Бренд *</span><input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="Например, COSRX" /></label>
              <label><span>Название *</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Например, Advanced Snail 96" /></label>
            </div>
          )}

          {method === "photo" && (
            <div className="scan-dropzone" onClick={pickPhoto}>
              <span className="scan__drop-icon"><Icon name="camera" size={26} /></span>
              <strong>{photoAdded ? "Фото загружено ✓" : "Сфотографировать упаковку"}</strong>
              <small>{photoAdded ? "Продукт распознан — нажмите «Проверить»." : "Наведите камеру на этикетку, чтобы распознать продукт и состав."}</small>
            </div>
          )}
          {method === "inci" && (
            <div className="scan-dropzone" onClick={pickPhoto}>
              <span className="scan__drop-icon"><Icon name="camera" size={26} /></span>
              <strong>{inciPhotoAdded ? "Состав распознан ✓" : "Сфотографировать состав"}</strong>
              <small>{inciPhotoAdded ? "Состав определён — нажмите «Проверить»." : "Наведите камеру на список состава (INCI) на упаковке."}</small>
            </div>
          )}
          {method === "link" && (
            <label className="scan-form__area">
              <span>Ссылка на продукт *</span>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onPaste={(e) => {
                  const raw = e.clipboardData.getData("text")
                  const found = extractUrl(raw)
                  if (found && found !== raw.trim()) {
                    e.preventDefault()
                    setUrl(found)
                  }
                }}
                placeholder="Вставьте ссылку — лишний текст уберём автоматически"
              />
            </label>
          )}
          {method === "manual" && (
            <>
              <label className="scan-form__area"><span>Состав (INCI) *</span><textarea value={inci} onChange={(e) => setInci(e.target.value)} placeholder="Вставьте полный состав…" rows={5} /></label>
              <div className="manual-photo">
                <span className="manual-photo__label">Фото продукта (необязательно)</span>
                {manualImage ? (
                  <div className="manual-photo__preview">
                    <img src={manualImage} alt="Фото продукта" />
                    <div className="manual-photo__actions">
                      <button type="button" className="chip" onClick={() => manualImageRef.current?.click()} disabled={manualImageBusy}>Заменить</button>
                      <button type="button" className="chip" onClick={() => { setManualImage(""); setManualImageError("") }} disabled={manualImageBusy}>Удалить</button>
                    </div>
                  </div>
                ) : (
                  <button type="button" className="manual-photo__add" onClick={() => manualImageRef.current?.click()} disabled={manualImageBusy}>
                    {manualImageBusy ? "Загружаем…" : "Прикрепить фото"}
                  </button>
                )}
                {manualImageError && <p className="manual-photo__error" role="alert">{manualImageError}</p>}
                <input ref={manualImageRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void uploadManualImage(file)
                  e.target.value = ""
                }} />
              </div>
            </>
          )}

          <Button icon="sparkle" onClick={run} disabled={!canRun} className="w-full">Проверить</Button>
          <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => {
            const file = e.target.files?.[0]
            if (!file) return
            if (method === "photo") takePhoto(file)
            else if (method === "inci") takeInciPhoto(file)
            e.target.value = ""
          }} />
        </section>
      )}

      {phase === "recognizing" && (
        <div className="scan-status">
          <span className="spin spin--lg" />
          <h3>Определяем продукт…</h3>
          <p>Сопоставляем название, бренд и состав.</p>
        </div>
      )}

      {phase === "ready" && result && (
        <div className="scan-ready panel">
          <p className="eyebrow">Продукт определён</p>
          <div className="scan-ready__row">
            <img src={result.image} alt="" />
            <div>
              <h3>{result.name}</h3>
              <p>{result.brand} · {result.category}</p>
              {result.match?.verdict && <VerdictPill verdict={result.match.verdict as Verdict} score={result.match.score} />}
            </div>
          </div>
          <div className="scan-form__row scan-ready__edit">
            <label><span>Бренд</span><input value={brand} onChange={(e) => setBrand(e.target.value)} /></label>
            <label><span>Название</span><input value={name} onChange={(e) => setName(e.target.value)} /></label>
          </div>
          <label className="scan-form__area"><span>Состав (INCI)</span><textarea value={inci} onChange={(e) => setInci(e.target.value)} rows={3} placeholder="Состав определится автоматически…" /></label>
          <div className="scan-ready__actions">
            <Button icon="sparkle" onClick={() => onContinue({ ...result, brand: brand.trim() || result.brand, name: name.trim() || result.name })}>Продолжить анализ</Button>
            <Button variant="ghost" onClick={() => setPhase("input")}>Не то — повторить</Button>
          </div>
        </div>
      )}
    </div>
  )
}
function CompatChart({ history }: { history: { step: number; label: string; shelfAverage: number }[] }) {
  const w = 560, h = 180, padL = 34, padR = 14, padT = 16, padB = 34
  const n = history.length
  const x = (i: number) => padL + (i / (n - 1)) * (w - padL - padR)
  const y = (v: number) => padT + (1 - v / 100) * (h - padT - padB)
  const pts = history.map((p, i) => `${x(i)},${y(p.shelfAverage)}`)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="compat-chart" role="img" aria-label="Средняя совместимость полки">
      {[0, 25, 50, 75, 100].map((v) => (
        <g key={v}>
          <line x1={padL} y1={y(v)} x2={w - padR} y2={y(v)} stroke="var(--border)" strokeWidth="1" />
          <text x={padL - 6} y={y(v) + 3} textAnchor="end" className="compat-chart__axis">{v}</text>
        </g>
      ))}
      <polyline points={pts.join(" ")} fill="none" stroke="var(--good)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {history.map((p, i) => (
        <g key={p.step}>
          <circle cx={x(i)} cy={y(p.shelfAverage)} r="4" fill="var(--surface)" stroke="var(--good)" strokeWidth="2" />
          <text x={x(i)} y={h - 12} textAnchor="middle" className="compat-chart__label">{p.step}</text>
        </g>
      ))}
    </svg>
  )
}

function ReportPage({ onOpen }: { onOpen: (p: Product) => void }) {
  const want = products.filter((p) => p.state === "want").slice(0, 3)
  return (
    <div className="page">
      <PageHeading eyebrow="Сводка" title="Отчёт" lead="Быстрое понимание состояния вашей косметики." />
      <section className="report-hero">
        <div className="report-hero__num"><strong>{shelfReport.average}</strong><span>%</span></div>
        <p>Средняя совместимость полки</p>
      </section>
      <div className="report-cols">
        <section className="panel">
          <h3 className="panel__h3">Что хорошо</h3>
          <ul className="obs">{shelfReport.good.map((g) => <li key={g}><Icon name="check" size={15} /><span>{g}</span></li>)}</ul>
        </section>
        <section className="panel">
          <h3 className="panel__h3">На что обратить внимание</h3>
          <ul className="obs obs--warn">{shelfReport.attention.map((g) => <li key={g}><span>{g}</span></li>)}</ul>
        </section>
      </div>
      <section className="block">
        <SectionHead eyebrow="Дальше" title="Проверьте ещё" />
        <div className="rec-list">
          {want.map((p) => (
            <button key={p.id} type="button" className="rec" onClick={() => onOpen(p)}>
              <img src={p.image} alt="" loading="lazy" />
              <span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>
              {p.match && <ScoreBadge score={p.match.score} verdict={p.match.verdict} recommendationStatus={p.match.recommendation_status} />}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}

function OptionChips({ options, selected, onToggle }: { options: QuizOption[]; selected: string[]; onToggle: (id: string) => void }) {
  return (
    <div className="quiz__options">
      {options.map((o) => {
        const on = selected.includes(o.id)
        return (
          <button key={o.id} type="button" className={`quiz__opt ${on ? "quiz__opt--on" : ""}`} onClick={() => onToggle(o.id)}>
            <span>{o.label}</span>
            {on && <Icon name="check" size={16} />}
          </button>
        )
      })}
    </div>
  )
}
function Questionnaire({ onDone }: { onDone: (p: { skinType: string; age?: string; concerns?: string[]; allergies?: string[]; structured?: Record<string, unknown> }) => void }) {
  const [step, setStep] = useState(0)
  const [skinType, setSkinType] = useState<string | null>(null)
  const [age, setAge] = useState<string | null>(null)
  const [cards, setCards] = useState<string[]>([])
  const [answers, setAnswers] = useState<Record<string, Record<string, string[]>>>({})
  const [therapy, setTherapy] = useState<string[]>([])
  const [retinoid, setRetinoid] = useState<string | null>(null)
  const [acids, setAcids] = useState<string[]>([])
  const [procedures, setProcedures] = useState<Record<string, string>>({})
  const [intolerances, setIntolerances] = useState<string[]>([])
  const [goals, setGoals] = useState<string[]>([])

  const steps = useMemo(() => {
    const s: { id: string; card?: QuizBranch }[] = [{ id: "skin" }, { id: "concerns" }]
    for (const c of cards) { const b = CONCERN_CARDS.find((x) => x.id === c); if (b) s.push({ id: "concern", card: b }) }
    s.push({ id: "therapy" }, { id: "procedures" }, { id: "intolerances" }, { id: "goals" }, { id: "summary" })
    return s
  }, [cards])

  const idx = Math.min(step, steps.length - 1)
  const current = steps[idx]
  const total = steps.length
  const toggleList = (list: string[], set: (v: string[]) => void, id: string) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])

  const canNext = (() => {
    if (current.id === "skin") return skinType != null
    if (current.id === "concern") return current.card!.questions.every((q) => (answers[current.card!.id]?.[q.id]?.length ?? 0) > 0)
    if (current.id === "goals") return goals.length > 0
    return true
  })()

  const next = () => setStep((s) => Math.min(s + 1, total - 1))
  const back = () => setStep((s) => Math.max(s - 1, 0))
  const TITLES: Record<string, string> = { skin: "Тип кожи", concerns: "Что беспокоит", therapy: "Активное лечение", procedures: "Процедуры", intolerances: "Непереносимости", goals: "Цели ухода", summary: "Готово" }
  const title = current.id === "concern" ? current.card!.shortLabel : TITLES[current.id] ?? ""

  return (
    <div className="quiz">
      <div className="quiz__progress"><span style={{ width: `${((idx + 1) / total) * 100}%` }} /></div>
      <p className="eyebrow">Шаг {idx + 1} из {total}</p>
      <h2 className="quiz__title">{title}</h2>

      {current.id === "skin" && (
        <>
          <p className="quiz__hint">Какой у вас тип кожи?</p>
          <OptionChips options={SKIN_TYPE_OPTIONS} selected={skinType ? [skinType] : []} onToggle={(id) => setSkinType(id)} />
          <p className="quiz__hint">Ваш возраст</p>
          <OptionChips options={AGE_OPTIONS} selected={age ? [age] : []} onToggle={(id) => setAge(id)} />
        </>
      )}

      {current.id === "concerns" && (
        <>
          <p className="quiz__hint">Выберите всё, что актуально — по каждому пункту зададим уточняющий вопрос.</p>
          <OptionChips options={CONCERN_CARDS.map((c) => ({ id: c.id, label: c.label }))} selected={cards} onToggle={(id) => toggleList(cards, setCards, id)} />
        </>
      )}

      {current.id === "concern" && current.card && (
        <div className="quiz__branch">
          {current.card.questions.map((q) => (
            <div key={q.id}>
              <p className="quiz__hint">{q.label}</p>
              <OptionChips options={q.options} selected={answers[current.card!.id]?.[q.id] ?? []} onToggle={(id) => {
                setAnswers((prev) => { const cur = prev[current.card!.id]?.[q.id] ?? []; const nxt = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]; return { ...prev, [current.card!.id]: { ...prev[current.card!.id], [q.id]: nxt } } })
              }} />
            </div>
          ))}
        </div>
      )}

      {current.id === "therapy" && (
        <div className="quiz__branch">
          <p className="quiz__hint">Используете ли активное лечение?</p>
          <OptionChips options={THERAPY_OPTIONS} selected={therapy} onToggle={(id) => toggleList(therapy, setTherapy, id)} />
          {therapy.includes("topical_retinoid") && (<><p className="quiz__hint">Какой ретиноид?</p><OptionChips options={RETINOID_OPTIONS} selected={retinoid ? [retinoid] : []} onToggle={(id) => setRetinoid(id)} /></>)}
          {therapy.includes("acid_therapy") && (<><p className="quiz__hint">Какие кислоты?</p><OptionChips options={ACID_OPTIONS} selected={acids} onToggle={(id) => toggleList(acids, setAcids, id)} /></>)}
        </div>
      )}

      {current.id === "procedures" && (
        <div className="quiz__branch">
          <p className="quiz__hint">Были ли недавно процедуры? Для выбранных уточните период.</p>
          {PROCEDURE_OPTIONS.map((o) => {
            const on = procedures[o.id] != null
            return (
              <div key={o.id} className="quiz__proc">
                <button type="button" className={`quiz__opt ${on ? "quiz__opt--on" : ""}`} onClick={() => setProcedures((prev) => { const c = { ...prev }; if (c[o.id]) delete c[o.id]; else c[o.id] = "<7"; return c })}>
                  <span>{o.label}</span>{on && <Icon name="check" size={16} />}
                </button>
                {on && o.id !== "none" && (
                  <div className="quiz__proc-periods">
                    {PROCEDURE_PERIODS.map((p) => (
                      <button key={p.id} type="button" className={`chip ${procedures[o.id] === p.id ? "chip--on" : ""}`} onClick={() => setProcedures((prev) => ({ ...prev, [o.id]: p.id }))}>{p.label}</button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {current.id === "intolerances" && (
        <>
          <p className="quiz__hint">Есть ингредиенты, которые вы избегаете?</p>
          <OptionChips options={INTOLERANCE_OPTIONS} selected={intolerances} onToggle={(id) => toggleList(intolerances, setIntolerances, id)} />
        </>
      )}

      {current.id === "goals" && (
        <>
          <p className="quiz__hint">Главное, к чему хотите прийти.</p>
          <OptionChips options={GOALS_OPTIONS} selected={goals} onToggle={(id) => toggleList(goals, setGoals, id)} />
        </>
      )}

      {current.id === "summary" && (
        <div className="quiz__summary">
          <div className="quiz__summary-row"><span>Тип кожи</span><strong>{SKIN_TYPE_OPTIONS.find((o) => o.id === skinType)?.label ?? "—"}</strong></div>
          <div className="quiz__summary-row"><span>Возраст</span><strong>{AGE_OPTIONS.find((o) => o.id === age)?.label ?? "—"}</strong></div>
          <div className="quiz__summary-row"><span>Проблемы</span><strong>{cards.length ? cards.map((c) => CONCERN_CARDS.find((b) => b.id === c)?.shortLabel).join(", ") : "—"}</strong></div>
          <div className="quiz__summary-row"><span>Лечение</span><strong>{therapy.length && !therapy.includes("none") ? therapy.map((t) => THERAPY_OPTIONS.find((o) => o.id === t)?.label).join(", ") : "—"}</strong></div>
          <div className="quiz__summary-row"><span>Процедуры</span><strong>{Object.keys(procedures).length ? Object.keys(procedures).map((p) => PROCEDURE_OPTIONS.find((o) => o.id === p)?.label).join(", ") : "—"}</strong></div>
          <div className="quiz__summary-row"><span>Непереносимости</span><strong>{intolerances.length ? intolerances.map((i) => INTOLERANCE_OPTIONS.find((o) => o.id === i)?.label).join(", ") : "—"}</strong></div>
          <div className="quiz__summary-row"><span>Цели</span><strong>{goals.map((g) => GOALS_OPTIONS.find((o) => o.id === g)?.label).join(", ")}</strong></div>
          <p className="quiz__summary-note">Этот профиль будет использоваться для расчёта совместимости каждого продукта.</p>
        </div>
      )}

      <div className="quiz__nav">
        {idx > 0 && <Button variant="ghost" icon="back" onClick={back}>Назад</Button>}
        <div className="quiz__nav-spacer" />
        {current.id === "summary" ? (
          <Button icon="check" onClick={() => {
            const structuredTherapy: { id: string; active: boolean }[] = []
            if (therapy.includes("topical_retinoid")) structuredTherapy.push({ id: retinoid ?? "topical_retinoid", active: true })
            if (therapy.includes("acid_therapy")) for (const a of acids) structuredTherapy.push({ id: a, active: true })
            for (const t of therapy) if (!["topical_retinoid", "acid_therapy", "none"].includes(t)) structuredTherapy.push({ id: t, active: true })
            const structured = {
              skin_type: skinType ?? "normal",
              age: age ?? undefined,
              concerns: cards,
              therapy: structuredTherapy,
              procedures: Object.entries(procedures).map(([id, period]) => ({ id, period })),
              // Stable questionnaire ids: Evaluation V2 keys knowledge by these,
              // not by the human-readable labels below (kept for the legacy API).
              intolerances,
              goals,
            }
            onDone({
              skinType: skinType ?? "normal",
              age: age ?? undefined,
              concerns: cards.map((c) => CONCERN_CARDS.find((b) => b.id === c)?.label ?? c),
              allergies: intolerances.map((i) => INTOLERANCE_OPTIONS.find((o) => o.id === i)?.label ?? i),
              structured,
            })
          }}>Сохранить профиль</Button>
        ) : (
          <Button disabled={!canNext} onClick={next}>Далее <Icon name="arrow" size={15} /></Button>
        )}
      </div>
    </div>
  )
}
function ProfilePage({ user, onAuth, onPricing, onLogout, onPoints, onDelete }: {
  user: User | null; onAuth: () => void; onPricing: () => void; onLogout: () => void; onPoints: () => void; onDelete: () => void
}) {
  const [quiz, setQuiz] = useState(false)
  const [skinType, setSkinType] = useState(getUserProfile().skinType)
  const [profileError, setProfileError] = useState("")
  if (quiz) {
    return (
      <div className="page">
        <PageHeading eyebrow="Профиль" title="Опрос кожи" lead="Несколько шагов — и профиль станет точнее." />
        <Questionnaire onDone={(p) => {
          const skinTypeLabel = SKIN_TYPE_OPTIONS.find((o) => o.id === p.skinType)?.label ?? p.skinType
          const pd = { skinType: skinTypeLabel, age: p.age ?? "", concerns: p.concerns ?? [], allergies: p.allergies ?? [], structured: p.structured ?? null }
          setUserProfile(pd)
          setSkinType(skinTypeLabel)
          setQuiz(false)
          if (getToken()) {
            setProfileError("")
            api.saveProfile({ skinType: skinTypeLabel, age: p.age ?? "", concerns: p.concerns ?? [], allergies: p.allergies ?? [], customText: "", structured: p.structured ?? undefined })
              .catch((error) => setProfileError(error instanceof Error ? error.message : "Не удалось сохранить профиль"))
          }
        }} />
      </div>
    )
  }
  if (!user) {
    return (
      <div className="page">
        <PageHeading eyebrow="Профиль" title="Профиль кожи" lead="Короткий профиль по типу кожи доступен гостю." />
        <div className="profile-grid">
          <section className="panel"><p className="eyebrow">Тип кожи</p><h3 className="panel__h3">{skinType}</h3></section>
          <section className="panel">
            <p className="eyebrow">Полный профиль</p>
            <h3 className="panel__h3">Только для аккаунта</h3>
            <p className="panel__note">Чувствительность, непереносимости, активное лечение и цели доступны после входа.</p>
            <Button icon="user" onClick={onAuth} className="mt">Войти / зарегистрироваться</Button>
            <Button variant="ghost" small icon="crown" onClick={onPricing} className="mt">Тарифы</Button>
          </section>
        </div>
      </div>
    )
  }
  const plan = PLANS.find((p) => p.key === user.plan)
  const structured = (getUserProfile().structured || {}) as Record<string, unknown>
  const structuredList = (key: string): string[] => {
    const value = structured[key]
    const raw = Array.isArray(value)
      ? value
      : value && typeof value === "object"
        ? Object.values(value as Record<string, unknown>)
        : []
    return raw.map((item) => {
      if (item && typeof item === "object") {
        const row = item as Record<string, unknown>
        return String(row.label || row.name || row.id || "").trim()
      }
      return String(item || "").trim()
    }).filter(Boolean)
  }
  const therapy = structuredList("therapy")
  const procedures = structuredList("procedures")
  const restrictions = structuredList("restrictions")
  return (
    <div className="page">
      <PageHeading eyebrow="Профиль" title="Профиль кожи" lead="На основе профиля рассчитывается совместимость каждого продукта."
        action={<div className="page-head__actions"><Button icon="user" onClick={() => setQuiz(true)}>Перепройти опрос</Button><Button variant="ghost" icon="logout" onClick={onLogout}>Выйти</Button><Button variant="ghost" onClick={onDelete}>Удалить аккаунт</Button></div>} />
      {profileError && <p className="evalv2__error" role="alert">{profileError}</p>}
      <div className="account-bar">
        <div><p className="eyebrow">Аккаунт</p><strong>{user.name}</strong><span>{user.points} баллов · тариф {plan?.title} · до {plan?.shelfLimit ?? 5} продуктов на полке</span></div>
        <div className="account-bar__actions">
          <Button variant="secondary" icon="credits" onClick={onPoints}>Пополнить баллы</Button>
          <Button variant="ghost" icon="crown" onClick={onPricing}>Управлять подпиской</Button>
        </div>
      </div>
      <div className="profile-grid">
        <section className="panel"><p className="eyebrow">Тип кожи</p><h3 className="panel__h3">{skinType}</h3></section>
        <section className="panel"><p className="eyebrow">Проблемы</p>{getUserProfile().concerns.length ? <div className="chips">{getUserProfile().concerns.map((g) => <span key={g} className="chip">{g}</span>)}</div> : <p className="panel__note">Не указаны</p>}</section>
        <section className="panel"><p className="eyebrow">Непереносимости</p>{getUserProfile().allergies.length ? <div className="chips">{getUserProfile().allergies.map((t) => <span key={t} className="chip">{t}</span>)}</div> : <p className="panel__note">Не указаны</p>}</section>
        <section className="panel"><p className="eyebrow">Лечение</p>{therapy.length ? <div className="chips">{therapy.map((t) => <span key={t} className="chip">{t}</span>)}</div> : <p className="panel__note">Не указано</p>}</section>
        <section className="panel"><p className="eyebrow">Процедуры</p>{procedures.length ? <div className="chips">{procedures.map((t) => <span key={t} className="chip">{t}</span>)}</div> : <p className="panel__note">Не указаны</p>}</section>
        <section className="panel"><p className="eyebrow">Ограничения</p>{restrictions.length ? <div className="chips">{restrictions.map((t) => <span key={t} className="chip">{t}</span>)}</div> : <p className="panel__note">Не указаны</p>}</section>
      </div>
      <section className="block"><p className="profile-note">Изменение профиля бесплатно. Сохранённые результаты не удаляются: устаревшие продукты можно обновить с полки одним пакетом.</p></section>
    </div>
  )
}
function ProductDrawer({ product, user, onAuth, onPricing, onClose, onChecking, onChecked, onCheckFinished, onReported, onOpen, onGoToCatalog, onAddToShelf, onRemove, onCategoryEdit, morphOrigin }: {
  product: Product; user: User | null; onAuth: () => void; onPricing: () => void; onClose: () => void;
  onChecking: (id: number) => void; onChecked: (id: number, score: number | null, verdict: Verdict | null, recommendationStatus?: string, analysisId?: number) => void; onCheckFinished: (id: number) => void; onReported: (id: number, analysisId?: number) => void; onOpen: (p: Product) => void; onGoToCatalog: (q: string, category?: string) => void;
  onAddToShelf: (p: Product) => Promise<boolean>; onRemove: (p: Product) => void; onCategoryEdit: (shelfId: number, category: string) => void; morphOrigin?: HTMLElement | null
}) {
  const [phase, setPhase] = useState<"idle" | "checking" | "match" | "generating" | "report">(
    product.match ? "match" : "idle"
  )
  const [score, setScore] = useState<number | null>(product.match?.score ?? null)
  const [verdict, setVerdict] = useState<Verdict | null>((product.match?.verdict as Verdict) ?? null)
  const [recommendationStatus, setRecommendationStatus] = useState<string | undefined>(product.match?.recommendation_status)
  const [closing, setClosing] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [cautionIngredients, setCautionIngredients] = useState<string[]>(product.match?.caution_ingredients ?? [])
  const [adding, setAdding] = useState(false)
  const [shelfError, setShelfError] = useState("")
  const [analysisId, setAnalysisId] = useState<number | undefined>(product.match?.analysis_id)
  const [reportData, setReportData] = useState<ReportResult | null>(null)
  const [showAnalysisExplainer, setShowAnalysisExplainer] = useState(false)
  const [v2Started, setV2Started] = useState(false)
  const [reportError, setReportError] = useState("")
  const [reviews, setReviews] = useState<Review[]>([])
  const [rating, setRating] = useState(0)
  const [review, setReview] = useState("")
  const [anonymous, setAnonymous] = useState(false)
  const [reviewSent, setReviewSent] = useState(false)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewError, setReviewError] = useState("")
  const drawerScrollRef = useRef<HTMLDivElement>(null)
  const morphDrawerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const source = morphOrigin
    const drawer = morphDrawerRef.current as HTMLElement | null
    if (!source || !source.isConnected || !drawer) return
    const from = source.getBoundingClientRect()
    const to = drawer.getBoundingClientRect()
    if (!from.width || !from.height || !to.width || !to.height) return

    const oldVisibility = drawer.style.visibility
    const oldAnimation = drawer.style.animation
    drawer.style.visibility = "hidden"
    drawer.style.animation = "none"

    const clone = source.cloneNode(true) as HTMLElement
    Object.assign(clone.style, {
      position: "fixed", left: `${from.left}px`, top: `${from.top}px`,
      width: `${from.width}px`, height: `${from.height}px`, margin: "0",
      boxSizing: "border-box", overflow: "hidden", pointerEvents: "none",
      zIndex: "2147483647", transform: "none",
      background: getComputedStyle(source).backgroundColor,
      boxShadow: getComputedStyle(source).boxShadow
    })
    document.body.appendChild(clone)

    // Плавно убираем только содержимое карточки, не её оболочку.
    Array.from(clone.children).forEach((node) => {
      if (
        node instanceof HTMLElement &&
        !node.matches(".autopick-carousel__swipe-tint, .autopick-carousel__swipe-hint")
      ) {
        node.animate([{ opacity: 1 }, { opacity: 0 }], {
          duration: 140, delay: 260, easing: "ease-out", fill: "forwards"
        })
      }
    })

    let finished = false
    const restore = () => {
      if (finished) return
      finished = true
      clone.remove()
      drawer.style.visibility = oldVisibility
      drawer.style.animation = oldAnimation

      // Проявляем внутренние элементы после завершения морфинга.
      Array.from(drawer.children).forEach((node) => {
        if (node instanceof HTMLElement) {
          node.animate([{ opacity: 0 }, { opacity: 1 }], {
            duration: 160, easing: "ease-out"
          })
        }
      })
    }
    const animation = clone.animate([
      { left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`,
        height: `${from.height}px`, borderRadius: getComputedStyle(source).borderRadius },
      { left: `${to.left}px`, top: `${to.top}px`, width: `${to.width}px`,
        height: `${to.height}px`, borderRadius: getComputedStyle(drawer).borderRadius }
    ], { duration: 420, easing: "cubic-bezier(.16,1,.3,1)", fill: "forwards" })
    animation.onfinish = restore
    animation.oncancel = restore
    return () => { animation.cancel(); restore() }
  }, [morphOrigin])

  useEffect(() => {
    if (showAnalysisExplainer) {
      drawerScrollRef.current?.scrollTo({ top: 0, behavior: "auto" })
    }
  }, [showAnalysisExplainer])


  useEffect(() => {
    let cancelled = false
    setReviews([])
    setReviewError("")
    setReviewSent(false)

    if (!product.slug) return

    api.reviews(product.slug)
      .then((result) => {
        if (!cancelled) {
          setReviews(Array.isArray(result.reviews) ? result.reviews : [])
        }
      })
      .catch(() => {
        if (!cancelled) setReviewError("Не удалось загрузить отзывы.")
      })

    return () => { cancelled = true }
  }, [product.slug])

   const submitReview = async () => {
    const text = review.trim()
    if (rating < 1 || rating > 5 || !text) {
      setReviewError("Поставьте оценку и напишите отзыв.")
      return
    }
    if (!user) {
      onAuth()
      return
    }

    setReviewLoading(true)
    setReviewError("")
    setReviewSent(false)
    if (!product.slug) {
      setReviewError("У продукта нет ссылки для отзыва.")
      setReviewLoading(false)
      return
    }
    try {
      await api.addReview(product.slug, rating, text, anonymous)
      const result = await api.reviews(product.slug)
      setReviews(Array.isArray(result.reviews) ? result.reviews : [])
      setReview("")
      setRating(0)
      setReviewSent(true)
    } catch {
      setReviewError("Не удалось отправить отзыв. Проверьте авторизацию и попробуйте ещё раз.")
    } finally {
      setReviewLoading(false)
    }
  }

  const addToShelf = async () => {
    setAdding(true)
    setShelfError("")
    try {
      const saved = await onAddToShelf(product)
      if (!saved) setShelfError("Не удалось добавить на полку. Проверьте соединение и попробуйте ещё раз.")
    } catch (error) {
      setShelfError(error instanceof Error && error.message
        ? error.message
        : "Не удалось добавить на полку. Проверьте соединение и попробуйте ещё раз.")
    } finally {
      setAdding(false)
    }
  }

  const close = () => {
    if (closing) return
    setClosing(true)

    const source = morphOrigin
    const drawer = morphDrawerRef.current
    if (source?.isConnected && drawer) {
      const from = drawer.getBoundingClientRect()
      const to = source.getBoundingClientRect()
      if (from.width && from.height && to.width && to.height) {
        const clone = drawer.cloneNode(true) as HTMLElement
        Object.assign(clone.style, {
          position: "fixed", left: `${from.left}px`, top: `${from.top}px`,
          width: `${from.width}px`, height: `${from.height}px`, margin: "0",
          boxSizing: "border-box", overflow: "hidden", pointerEvents: "none",
          zIndex: "2147483647", transform: "none", visibility: "visible",
          animation: "none"
        })
        clone.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"))
        document.body.appendChild(clone)

        // Содержимое drawer растворяется отдельно от движущейся оболочки.
        Array.from(clone.children).forEach((node) => {
          if (node instanceof HTMLElement) {
            node.animate([{ opacity: 1 }, { opacity: 0 }], {
              duration: 140, delay: 260, easing: "ease-out", fill: "forwards"
            })
          }
        })

        const oldVisibility = drawer.style.visibility
        const oldAnimation = drawer.style.animation
        drawer.style.visibility = "hidden"
        drawer.style.animation = "none"
        if (source instanceof HTMLElement) source.style.visibility = "hidden"

        const animation = clone.animate([
          { left: `${from.left}px`, top: `${from.top}px`,
            width: `${from.width}px`, height: `${from.height}px`,
            borderRadius: "0px" },
          { left: `${to.left}px`, top: `${to.top}px`,
            width: `${to.width}px`, height: `${to.height}px`,
            borderRadius: getComputedStyle(source).borderRadius }
        ], { duration: 420, easing: "cubic-bezier(.16,1,.3,1)", fill: "forwards" })

        let finished = false
        const finish = () => {
          if (finished) return
          finished = true
          clone.remove()
          drawer.style.visibility = oldVisibility
          drawer.style.animation = oldAnimation
          if (source instanceof HTMLElement) {
            source.style.visibility = ""

            // Возвращаем содержимое исходной карточки мягким появлением.
            Array.from(source.children).forEach((node) => {
              if (
                node instanceof HTMLElement &&
                !node.matches(".autopick-carousel__swipe-tint, .autopick-carousel__swipe-hint")
              ) {
                node.animate([{ opacity: 0 }, { opacity: 1 }], {
                  duration: 160, easing: "ease-out"
                })
              }
            })
          }
        }
        animation.onfinish = finish
        animation.oncancel = finish
        window.setTimeout(onClose, 420)
        return
      }
    }

    window.setTimeout(onClose, 320)
  }

  const check = async () => {
    setPhase("checking")
    onChecking(product.id)
    try {
      let res
      if (product.slug) {
        // Продукт из каталога — проверяем по имени; бэкенд сохранит анализ (для полки).
        res = await api.check({ product_name: product.name, skin_type: getUserProfile().skinType, profile: buildProfile() })
      } else {
        const inci = product.ingredients || ""
        if (inci.trim()) {
          res = await api.checkWithIngredients({ product_name: product.name, skin_type: getUserProfile().skinType, profile: buildProfile(), ingredients: inci })
        } else {
          res = await api.check({ product_name: product.name, skin_type: getUserProfile().skinType, profile: buildProfile() })
        }
      }
      console.log("CHECK RES:", res);
      const recStatus = res.recommendation_status
      const rawScore = typeof res.score === "number" ? res.score : null
      const aid = typeof res.analysis_id === "number" ? res.analysis_id : undefined
      if (Array.isArray(res.caution_ingredients)) setCautionIngredients(res.caution_ingredients)

      let finalVerdict: Verdict | null
      let finalScore: number | null
      if (recStatus === "Не рекомендовано") {
        finalVerdict = "Не рекомендовано"
        finalScore = rawScore
      } else if (recStatus === "Недостаточно данных" || recStatus === "Не оценивается") {
        finalVerdict = null
        finalScore = null
      } else if (rawScore != null) {
        finalVerdict = mapVerdict(rawScore, res.verdict) ?? "Подходит частично"
        finalScore = rawScore
      } else {
        // Неожиданный ответ без score и известного статуса — не выдумываем результат.
        setPhase("idle")
        return
      }

      setScore(finalScore); setVerdict(finalVerdict); setRecommendationStatus(recStatus); setAnalysisId(aid); setReportData(null); setPhase("match")
      onChecked(product.id, finalScore, finalVerdict, recStatus, aid)
    } catch {
      // Ошибка проверки — не выдумываем результат, но завершаем состояние загрузки.
      setPhase("idle")
    } finally {
      onCheckFinished(product.id)
    }
  }

  const showReport = async () => {
    if (!user) { onAuth(); return }
    if (user.plan === "free") { onPricing(); return }
    // Повторное нажатие сворачивает уже раскрытый отчёт, карточка не меняется.
    if (reportData) { setReportData(null); return }
    // Недостаточно состава — это отдельное состояние, а не «нет анализа».
    if (
      recommendationStatus === "Недостаточно данных"
      || recommendationStatus === "Не оценивается"
      || (score == null && product.match == null)
    ) {
      setReportError(
        recommendationStatus === "Не оценивается"
          ? "Для этой категории отчёт о кожной совместимости не формируется."
          : "Недостаточно данных о составе: отчёт недоступен. Добавьте полный состав и проверьте снова."
      )
      return
    }
    // Отчёт можно получить по analysis_id даже если у продукта нет slug
    // (вручную добавленный продукт, которого ещё нет в каталоге).
    let aid = analysisId ?? product.match?.analysis_id
    if (aid == null && product.slug) {
      try {
        const d = await api.product(product.slug)
        const a = (d.analysis || {}) as { id?: number }
        aid = typeof a.id === "number" ? a.id : undefined
      } catch { aid = undefined }
    }
    if (aid == null && !product.slug) {
      setReportError("Для этого продукта ещё нет сохранённого анализа. Запустите проверку состава.")
      return
    }
    setReportError("")
    // Карточка остаётся на месте: крутим загрузку в кнопке, отчёт раскрывается ниже.
    setReportLoading(true)
    try {
      const res = await api.analysisReport(product.slug || "", aid)
      setReportData(res)
      if (typeof res.score === "number") setScore(res.score)
      setAnalysisId(aid)
      onReported(product.id, aid)
    } catch (e) {
      // Разные причины — разные сообщения. 401/403 — сессия, 409 — нет анализа,
      // остальное (включая 502) — временный сбой генерации.
      const status = e instanceof ApiError ? e.status : 0
      const detail = e instanceof Error && e.message ? e.message : ""
      if (status === 401 || status === 403) {
        setReportError("Сессия истекла. Войдите снова, чтобы открыть отчёт.")
        onAuth()
      } else if (status === 409) {
        setReportError(detail || "Анализ ещё не выполнен — сначала проверьте совместимость.")
      } else {
        setReportError("Не удалось сформировать отчёт. Попробуйте ещё раз через минуту.")
      }
    } finally {
      setReportLoading(false)
    }
  }

  const handleShowReport = () => {
    void showReport()
  }

  return (
    <>
      <div className={`drawer-backdrop ${closing ? "drawer-backdrop--closing" : ""}`} onClick={close} />
      <aside ref={morphDrawerRef} className={`drawer ${closing ? "drawer--closing" : ""}`} role="dialog" aria-modal="true">
        <button type="button" className="drawer__close" onClick={close} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="drawer__scroll" ref={drawerScrollRef}>
          <div className="drawer__hero">
            <ProductImage src={product.image} className="drawer__hero-image" />

            <div className="drawer__hero-meta">
              <button type="button" className="drawer__brand-link" onClick={() => onGoToCatalog(product.brand)}>{product.brand}</button>
              <h2>{product.name}</h2>
              {product.verified && <span className="drawer__verified"><Icon name="check" size={12} /> Проверенный продукт</span>}
              <button type="button" className="drawer__cat drawer__cat--link" onClick={() => onGoToCatalog(product.category, product.category)}>{product.subcategory ? `${product.category} · ${product.subcategory}` : product.category}</button>
            </div>
          </div>


          {EVALUATION_V2_ENABLED && !!user && (phase === "idle" || phase === "match") && (
            <div className="drawer__body">
              <EvaluationV2Panel
                productId={product.id}
                profile={buildProfile()}
                canRestore={product.verified !== false}
                onStarted={() => setV2Started(true)}
              />
            </div>
          )}

{(product.barcode || product.variant) && (
                <section className="report-card">
                  <h4>Данные упаковки</h4>
                  {product.variant && <p className="drawer__report-summary">Вариант: {product.variant}</p>}
                  {product.barcode && <p className="drawer__report-summary">Штрихкод: {product.barcode}</p>}
                </section>
              )}

{product.ingredients && (
              <section className="report-card drawer__inci">
                <h4>Состав (INCI)</h4>
                <p className="inci">
                  {highlightInci(product.ingredients, cautionIngredients)}
                </p>
              </section>
              )}

              {product.slug && (
                <section className="drawer__review">
                  <h3>Отзывы о продукте</h3>

                  {reviews.length > 0 ? (
                    <>
                      <div className="drawer__review-summary">
                        <strong>
                          {(reviews.reduce((sum, item) => sum + item.rating, 0) / reviews.length).toFixed(1)}
                        </strong>
                        <span className="stars" aria-label="Средняя оценка">
                          {"★".repeat(Math.round(reviews.reduce((sum, item) => sum + item.rating, 0) / reviews.length))}
                          {"☆".repeat(5 - Math.round(reviews.reduce((sum, item) => sum + item.rating, 0) / reviews.length))}
                        </span>
                        <span>{reviews.length} {reviews.length === 1 ? "отзыв" : reviews.length < 5 ? "отзыва" : "отзывов"}</span>
                      </div>

                      <div className="drawer__review-list">
                        {reviews.map((item) => (
                          <article className="drawer__review-item" key={item.id}>
                            <div className="drawer__review-meta">
                              <strong>{item.is_anonymous ? "Анонимный пользователь" : (item.author_name || "Пользователь")}</strong>
                              {item.created_at && (
                                <time>
                                  {Number.isNaN(Date.parse(item.created_at)) ? "" : new Date(item.created_at).toLocaleDateString("ru-RU")}
                                </time>
                              )}
                            </div>
                            <div className="stars" aria-label={`Оценка: ${item.rating} из 5`}>
                              <span className="star star--on">{"★".repeat(Math.max(0, Math.min(5, item.rating)))}</span>
                              <span className="star">{"☆".repeat(5 - Math.max(0, Math.min(5, item.rating)))}</span>
                            </div>
                            {item.text && <p className="drawer__review-text">{item.text}</p>}
                          </article>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="drawer__review-empty">Пока нет отзывов. Поделитесь первым впечатлением.</p>
                  )}

                  <div className="drawer__review-form">
                    <h4>Оставить отзыв</h4>
                    <span className="drawer__review-hint">Ваша оценка</span>
                    <div className="stars" role="group" aria-label="Ваша оценка от 1 до 5">
                      {[1, 2, 3, 4, 5].map((value) => (
                        <button
                          type="button"
                          className={`star ${value <= rating ? "star--on" : ""}`}
                          key={value}
                          aria-label={`${value} из 5`}
                          aria-pressed={rating === value}
                          onClick={() => setRating(value)}
                        >
                          {value <= rating ? "★" : "☆"}
                        </button>
                      ))}
                    </div>
                    <textarea
                      className="review-input"
                      value={review}
                      onChange={(event) => setReview(event.target.value)}
                      placeholder="Поделитесь впечатлением о продукте…"
                      rows={4}
                      maxLength={3000}
                    />
                    <label className="review-anon">
                      <input
                        type="checkbox"
                        checked={anonymous}
                        onChange={(event) => setAnonymous(event.target.checked)}
                      />
                      Опубликовать анонимно
                    </label>

                    {reviewError && <p className="drawer__review-error" role="status">{reviewError}</p>}
                    {reviewSent && <p className="drawer__review-success" role="status">Спасибо! Отзыв отправлен.</p>}

                    <button
                      type="button"
                      className="button button--primary"
                      disabled={reviewLoading || rating === 0 || !review.trim()}
                      onClick={submitReview}
                    >
                      {reviewLoading ? "Отправляем…" : user ? "Опубликовать отзыв" : "Войти и оставить отзыв"}
                    </button>
                  </div>
                </section>
              )}

                  {showAnalysisExplainer && (
            <div className="drawer__body drawer__analysis-explainer">
              <button type="button" className="drawer__back-link"
                onClick={() => setShowAnalysisExplainer(false)}>
                <span aria-hidden="true">←</span> Назад к результату
              </button>
              <p className="eyebrow">ПРОЗРАЧНЫЙ ПОДХОД</p>
              <h3>Как мы оцениваем совместимость?</h3>
              <p className="drawer__explain-intro">
                Мы сопоставляем состав косметического средства с вашим профилем,
                чтобы объяснить, насколько продукт может вам подойти.
              </p>
              <div className="drawer__analysis-step">
                <span>01</span><div><h4>Разбираем состав</h4>
                <p>Анализируем ингредиенты и доступные данные об их свойствах.</p></div>
              </div>
              <div className="drawer__analysis-step">
                <span>02</span><div><h4>Учитываем ваш профиль</h4>
                <p>Сопоставляем состав с указанными особенностями кожи и целями ухода.</p></div>
              </div>
              <div className="drawer__analysis-step">
                <span>03</span><div><h4>Оцениваем совместимость</h4>
                <p>Score Engine объединяет учитываемые факторы в итоговую оценку.</p></div>
              </div>
              <div className="drawer__analysis-step">
                <span>04</span><div><h4>Объясняем результат</h4>
                <p>В отчёте показываем факторы, повышающие или снижающие оценку.</p></div>
              </div>
              <p className="drawer__explain-disclaimer">
                Это оценка совместимости состава с вашим профилем, а не медицинская
                диагностика. Индивидуальная реакция кожи может отличаться.
              </p>
            </div>
          )}
        </div>
        
<div className={showAnalysisExplainer ? "drawer__footer drawer__footer--hidden" : "drawer__footer"}>
          <div className="drawer__footer-main">
            {product.shelf_id ? (
              <Button variant="ghost" onClick={() => onRemove(product)}>Убрать с полки</Button>
            ) : (
              <Button variant="secondary" icon="plus" onClick={addToShelf} disabled={adding}>{adding ? "Сохраняем…" : "На полку"}</Button>
            )}
            <Button variant="ghost" onClick={close}>Закрыть</Button>
          </div>
          {shelfError && <p className="drawer__shelf-error" role="alert">{shelfError}</p>}
        </div>
      </aside>
    </>
  )
}
function AuthModal({ mode, onClose, onSuccess, onSwitch }: {
  mode: "login" | "register"; onClose: () => void; onSuccess: (u: User) => void; onSwitch: (m: "login" | "register") => void
}) {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [pass, setPass] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  // Согласие с офертой: по умолчанию НЕ отмечено.
  const [acceptOffer, setAcceptOffer] = useState(false)

  const submit = async () => {
    setError("")
    if (!email.trim() || !pass) { setError("Введите email и пароль"); return }
    if (mode === "register" && !name.trim()) { setError("Введите имя"); return }
    if (mode === "register" && !acceptOffer) {
      setError("Примите условия публичной оферты, чтобы продолжить")
      return
    }
    setLoading(true)
    try {
      if (mode === "login") {
        const res = await api.login(email.trim(), pass)
        setToken(res.access_token)
        const displayName = res.user.name || email.trim().split("@")[0]
        const plan: Plan = res.user.plan === "pro" || res.user.plan === "plus" ? res.user.plan : "free"
        onSuccess({ name: displayName, initials: displayName.slice(0, 2).toUpperCase(), plan, points: res.user.balance || 0 })
      } else {
        const res = await api.register(email.trim(), pass, name.trim(), acceptOffer)
        if (res.access_token) {
          setToken(res.access_token)
          const displayName = (res.user && res.user.name) || name.trim() || email.trim().split("@")[0]
          const plan: Plan = res.user && (res.user.plan === "pro" || res.user.plan === "plus") ? res.user.plan : "free"
          onSuccess({ name: displayName, initials: displayName.slice(0, 2).toUpperCase(), plan, points: (res.user && res.user.balance) || 0 })
        } else {
          setSent(true)
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка")
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
          <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
          <div className="auth-modal">
            <p className="eyebrow">айдерми</p>
            <h2>Проверьте почту</h2>
            <p className="auth-modal__hint">Мы отправили письмо для подтверждения на {email}. После подтверждения войдите в аккаунт.</p>
            <Button variant="ghost" onClick={onClose} className="w-full">Закрыть</Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="auth-modal">
          <p className="eyebrow">айдерми</p>
          <h2>{mode === "login" ? "Вход" : "Регистрация"}</h2>
          <p className="auth-modal__hint">{mode === "login" ? "Войдите, чтобы видеть полку, баллы и отчёты." : "Создайте аккаунт — получите баллы и личную полку."}</p>
          {mode === "register" && (
            <label className="field"><span>Имя</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ольга" /></label>
          )}
          <label className="field"><span>Email</span><input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></label>
          <label className="field"><span>Пароль</span><input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="••••••••" /></label>
          {mode === "register" && (
            <label className="legal-consent">
              <input
                type="checkbox"
                checked={acceptOffer}
                onChange={(e) => setAcceptOffer(e.target.checked)}
              />
              <span>
                Принимаю{" "}
                <a href="/offer" target="_blank" rel="noopener noreferrer">публичную оферту</a>{" "}
                и{" "}
                <a href="/privacy" target="_blank" rel="noopener noreferrer">политику обработки персональных данных</a>
              </span>
            </label>
          )}
          {error && <p className="auth-modal__error">{error}</p>}
          <Button className="w-full" onClick={submit} disabled={loading}>{loading ? "Подождите…" : mode === "login" ? "Войти" : "Зарегистрироваться"}</Button>
          <div className="auth-modal__divider">или</div>
          <a href="/api/auth/google" className="google-btn">
            <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"/><path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A11 11 0 0 0 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/></svg>
            Войти через Google
          </a>
          <a href="/api/auth/yandex" className="google-btn google-btn--yandex">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="#FC3F1D" d="M13.32 21h3.02V3h-4.6c-3.1 0-4.9 1.85-4.9 4.6 0 2.2 1 3.6 2.9 4.7L6 21h2.9l3.3-8.1 1.1.7V21zm-.05-9.9-1.2-.8c-1.2-.8-1.9-1.7-1.9-3 0-1.6 1-2.6 2.7-2.6h.4v6.4z"/></svg>
            Войти через Яндекс
          </a>
          <button type="button" className="auth-modal__switch" onClick={() => onSwitch(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "Нет аккаунта? Зарегистрируйтесь" : "Уже есть аккаунт? Войдите"}
          </button>
        </div>
      </div>
    </div>
  )
}

function PricingModal({ user, onClose, onSelectPlan }: {
  user: User | null; onClose: () => void; onSelectPlan: (p: Plan) => void
}) {
  const currentPlan = user?.plan ?? "free"
  const [catalog, setCatalog] = useState<{ prices_defined: boolean; note: string } | null>(null)
  // Согласие перед оплатой: по умолчанию НЕ отмечено.
  const [acceptPayments, setAcceptPayments] = useState(false)
  const [checkoutError, setCheckoutError] = useState("")
  const [checkingOut, setCheckingOut] = useState(false)

  useEffect(() => {
    api.billingCatalog().then((c) => setCatalog(c)).catch(() => setCatalog(null))
  }, [])

  const canBuy = Boolean(catalog?.prices_defined)

  const handleCheckout = async (plan: Plan) => {
    if (!acceptPayments) { setCheckoutError("Подтвердите условия оплаты"); return }
    setCheckoutError("")
    setCheckingOut(true)
    try {
      await api.recordConsent("offer", "checkout")
      await api.createOrder({ plan })
      onSelectPlan(plan)
    } catch (e) {
      setCheckoutError(e instanceof Error ? e.message : "Оплата пока недоступна")
    } finally {
      setCheckingOut(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--wide" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="pricing">
          <p className="eyebrow">Подписка</p>
          <h2>Тарифы</h2>
          <p className="pricing__hint">Сравните возможности тарифов и выберите подходящий. Текущий тариф выделен цветом.</p>
          <div className="payment-note">
            <p>{catalog?.note || "Цены ещё не утверждены. Покупка недоступна до публикации цен."}</p>
            <p>
              Условия:{" "}
              <a href="/payment" target="_blank" rel="noopener noreferrer">оплата и возвраты</a>
              {" · "}
              <a href="/offer" target="_blank" rel="noopener noreferrer">публичная оферта</a>
            </p>
          </div>
          <label className="legal-consent">
            <input type="checkbox" checked={acceptPayments} onChange={(e) => setAcceptPayments(e.target.checked)} />
            <span>Принимаю условия оплаты и публичной оферты</span>
          </label>
          {checkoutError && <p className="auth-modal__error" role="alert">{checkoutError}</p>}
          <div className="matrix">
            <div className="matrix__row matrix__row--head">
              <span>Возможность</span>
              {PLANS.map((p) => (
                <span key={p.key} className={`matrix__plan ${currentPlan === p.key ? "matrix__plan--current" : ""}`}>{p.title}{currentPlan === p.key ? " · текущий" : ""}</span>
              ))}
            </div>
            {SUBSCRIPTION_ROWS.map((r) => (
              <div className="matrix__row" key={r.feature}>
                <span>{r.feature}</span>
                {PLANS.map((p) => {
                  const val = r.values[p.key]
                  const current = currentPlan === p.key
                  return (
                    <span key={p.key} className={`${val === "✓" ? "matrix__yes" : ""} ${current ? "matrix__cell--current" : ""}`}>{val}</span>
                  )
                })}
              </div>
            ))}
          </div>
          <div className="pricing-cards">
            {PLANS.map((p) => {
              const current = currentPlan === p.key
              return (
                <div key={p.key} className={`pricing-card ${current ? "pricing-card--current" : ""}`}>
                  <div className="pricing-card__head">
                    <strong>{p.title}</strong>
                    <span>{current ? "Текущий тариф" : `${p.monthlyPoints} баллов/мес`}</span>
                  </div>
                  <ul>
                    {SUBSCRIPTION_ROWS.map((r) => (
                      <li key={r.feature}><span>{r.feature}</span><b>{r.values[p.key]}</b></li>
                    ))}
                  </ul>
                  {p.key !== "free" && (
                    canBuy ? (
                      <Button
                        small
                        variant={p.key === "pro" ? "primary" : "secondary"}
                        onClick={() => handleCheckout(p.key)}
                        disabled={current || !acceptPayments || checkingOut}
                      >
                        {current ? "Текущий" : checkingOut ? "Оформляем…" : `Оплатить ${p.title}`}
                      </Button>
                    ) : (
                      <Button small variant="secondary" disabled>
                        {current ? "Текущий" : "Цена не утверждена"}
                      </Button>
                    )
                  )}
                </div>
              )
            })}
          </div>
          <p className="pricing__note">{EXTRA_POINTS_NOTE}</p>
          <div className="pricing__actions">
            {PLANS.filter((p) => p.key !== "free").map((p) => (
              <Button key={p.key} variant={p.key === "pro" ? "primary" : "secondary"} onClick={() => onSelectPlan(p.key)} disabled={user?.plan === p.key}>
                {user?.plan === p.key ? `${p.title} — текущий` : `Перейти на ${p.title}`}
              </Button>
            ))}
            <Button variant="ghost" onClick={onClose}>Закрыть</Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function LoadingScreen({ done }: { done: boolean }) {
  const [hide, setHide] = useState(false)
  useEffect(() => {
    if (done) { const t = window.setTimeout(() => setHide(true), 350); return () => window.clearTimeout(t) }
  }, [done])
  if (hide) return null
  return (
    <div className={`loading-screen ${done ? "loading-screen--done" : ""}`}>
      <img src={loadingGif} alt="Загрузка…" />
    </div>
  )
}
function PointsModal({ user, onClose, onTopUp }: { user: User | null; onClose: () => void; onTopUp: (amount: number) => void }) {
  const [done, setDone] = useState<number | null>(null)
  const PACKAGES = [
    { amount: 20, price: "99 ₽" },
    { amount: 50, price: "199 ₽" },
    { amount: 100, price: "349 ₽" },
    { amount: 300, price: "899 ₽" },
  ]
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="points-modal">
          <p className="eyebrow">Баллы</p>
          <h2>Пополнить баллы</h2>
          <p className="points-modal__hint">Сейчас у вас: <strong>{user?.points ?? 0} баллов</strong>. Выберите пакет.</p>
          <div className="points-packages">
            {PACKAGES.map((p) => (
              <button key={p.amount} type="button" className="points-package" onClick={() => { onTopUp(p.amount); setDone(p.amount) }}>
                <strong>+{p.amount}</strong><span>баллов</span><small>{p.price}</small>
              </button>
            ))}
          </div>
          {done != null && <p className="points-modal__done">✓ Добавлено {done} баллов</p>}
        </div>
      </div>
    </div>
  )
}

function ShelfAddModal({
  items,
  onClose,
  onAdd,
  onScan,
  onOpen,
  onPickReady,
  onGoToCatalog,
}: {
  items: Product[]
  onClose: () => void
  onAdd: (p: Product) => void
  onScan: (m: ScanMethod) => void
  onOpen: (p: Product) => void
  onPickReady: (products: Product[]) => void
  onGoToCatalog: () => void
}) {
  const [mode, setMode] = useState<"menu" | "catalog" | "auto">("menu")
  const [q, setQ] = useState("")
  const [recCat, setRecCat] = useState("")
  const [recs, setRecs] = useState<Product[]>([])
  const [recsLoading, setRecsLoading] = useState(false)
  const [catResults, setCatResults] = useState<Product[] | null>(null)
  const [catLoading, setCatLoading] = useState(false)

  const dragStartY = useRef<number | null>(null)
  const dragCurrentY = useRef<number | null>(null)
  const [dragY, setDragY] = useState(0)
  const [isClosing, setIsClosing] = useState(false)

  const [viewTransition, setViewTransition] = useState<"idle" | "out" | "in">("idle")
  const [sheetHeight, setSheetHeight] = useState<number | null>(null)

  const sheetRef = useRef<HTMLDivElement | null>(null)
  const transitionTimer = useRef<number | null>(null)


  useEffect(() => {
    if (mode !== "auto" || !recCat || !getToken()) {
      setRecs([])
      return
    }

    setRecsLoading(true)

    api.shelfRecommend("face", recCat)
      .then((r) => {
        setRecs(
          (r.recommendations || [])
            .map((x) => mapRecommendation(x as Parameters<typeof mapRecommendation>[0], recCat))
        )
      })
      .catch(() => setRecs([]))
      .finally(() => setRecsLoading(false))
  }, [mode, recCat])

  useEffect(() => {
    if (mode !== "catalog") {
      setCatResults(null)
      setCatLoading(false)
      return
    }

    const n = q.trim()

    if (!n) {
      setCatResults(null)
      setCatLoading(false)
      return
    }

    setCatLoading(true)

    const t = window.setTimeout(async () => {
      try {
        const res = await api.catalog({ search: n, limit: 30 })
        setCatResults(
          (res.products || [])
            .map(mapApiProduct)
            .filter((p) => p.name && p.name !== "Продукт")
        )
      } catch {
        setCatResults([])
      }

      setCatLoading(false)
    }, 250)

    return () => window.clearTimeout(t)
  }, [mode, q])



  const list = mode === "auto"
    ? recs.slice(0, 8)
    : catResults != null
      ? catResults.slice(0, 12)
      : items.filter((p) => !p.state).slice(0, 12)

  const getSheetHeight = () => {
    const el = sheetRef.current
    if (!el) return null

    const content = el.querySelector(".add-modal") as HTMLElement | null
    if (!content) return null

    const maxHeight =
      window.innerWidth <= 700
        ? window.innerHeight * 0.92
        : Math.min(820, window.innerHeight - 64)

    const naturalHeight = content.scrollHeight

    return Math.min(Math.ceil(naturalHeight), maxHeight)
  }

  const switchMode = (next: "menu" | "catalog" | "auto") => {
    if (mode === next || viewTransition !== "idle") return

    if (transitionTimer.current != null) {
      window.clearTimeout(transitionTimer.current)
    }

    const el = sheetRef.current
    if (!el) return

    const content = el.querySelector(".add-modal") as HTMLElement | null
    if (!content) return

    const maxHeight =
      window.innerWidth <= 700
        ? window.innerHeight * 0.92
        : Math.min(820, window.innerHeight - 64)

    const oldHeight = Math.min(
      Math.ceil(el.getBoundingClientRect().height),
      maxHeight
    )

    // Фиксируем текущий размер непосредственно в DOM.
    el.style.height = `${oldHeight}px`
    el.style.transition =
      "height .72s cubic-bezier(.22,1,.36,1), transform .65s cubic-bezier(.22,1,.36,1)"

    setViewTransition("out")

    transitionTimer.current = window.setTimeout(() => {
      setMode(next)

      requestAnimationFrame(() => {
        const newEl = sheetRef.current
        if (!newEl) return

        const newContent = newEl.querySelector(".add-modal") as HTMLElement | null
        if (!newContent) return

        // Временно убираем ограничение, чтобы получить реальную высоту контента.
        const previousMaxHeight = newEl.style.maxHeight
        newEl.style.maxHeight = "none"

        const newHeight = Math.min(
          Math.ceil(newContent.scrollHeight),
          maxHeight
        )

        newEl.style.maxHeight = previousMaxHeight

        // Принудительно фиксируем старое состояние layout.
        newEl.style.height = `${oldHeight}px`
        void newEl.offsetHeight

        // Теперь браузер гарантированно видит:
        // oldHeight -> newHeight.
        newEl.style.height = `${newHeight}px`

        setViewTransition("in")

        transitionTimer.current = window.setTimeout(() => {
          if (sheetRef.current) {
            sheetRef.current.style.height = ""
            sheetRef.current.style.transition = ""
          }

          setViewTransition("idle")
          transitionTimer.current = null
        }, 760)
      })
    }, 190)
  }

  useEffect(() => {
    return () => {
      if (transitionTimer.current != null) {
        window.clearTimeout(transitionTimer.current)
      }
    }
  }, [])

  const closeWithAnimation = () => {
    if (isClosing) return

    setIsClosing(true)
    setDragY(window.innerHeight)

    window.setTimeout(() => {
      onClose()
    }, 650)
  }

  const gestureRef = useRef<{ x: number; y: number; cancelled: boolean } | null>(null)

  const scrollerAtTop = () => {
    const el = sheetRef.current
    if (!el) return true
    const scroller = el.querySelector(".add-modal") as HTMLElement | null
    return !scroller || scroller.scrollTop <= 0
  }

  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    if (isClosing) return
    const t = e.touches[0]
    if (!t) return
    const target = e.target as HTMLElement | null
    const insideScroller = !!target?.closest(".add-modal")
    // Внутри прокрученного списка жест принадлежит списку, а не панели.
    if (insideScroller && !scrollerAtTop()) { gestureRef.current = null; return }
    gestureRef.current = { x: t.clientX, y: t.clientY, cancelled: false }
    dragStartY.current = t.clientY
    dragCurrentY.current = t.clientY
  }

  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    const g = gestureRef.current
    if (!g || g.cancelled) return
    const t = e.touches[0]
    if (!t) return
    const dx = t.clientX - g.x
    const dy = t.clientY - g.y
    // Горизонтальный жест (свайп карусели/списка) не должен закрывать панель.
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 12) {
      g.cancelled = true
      dragStartY.current = null
      dragCurrentY.current = null
      setDragY(0)
      return
    }
    dragCurrentY.current = t.clientY
    if (dy > 0) setDragY(Math.min(dy, window.innerHeight))
  }

  const handleTouchEnd = () => {
    const g = gestureRef.current
    gestureRef.current = null
    if (!g) return
    const delta = dragStartY.current != null && dragCurrentY.current != null
      ? dragCurrentY.current - dragStartY.current
      : 0
    dragStartY.current = null
    dragCurrentY.current = null
    if (!g.cancelled && (delta > 100 || dragY > 100)) {
      closeWithAnimation()
      return
    }
    setDragY(0)
  }


  const title =
    mode === "catalog"
      ? "Из каталога"
      : mode === "auto"
        ? "Автоподбор"
        : "Добавить средство"

  return (
    <div
      className={`modal-backdrop modal-backdrop--shelf-add${isClosing ? " is-closing" : ""}`}
      onClick={closeWithAnimation}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
      <div className="shelf-add-sheet-enter">
        <div
        ref={sheetRef}
          className={`modal modal--shelf-add modal--shelf-${mode} modal--shelf-transition-${viewTransition}`}
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.stopPropagation()}
          style={{
            transform: `translate3d(0, ${dragY}px, 0)`,
            transition: dragStartY.current
              ? "none"
              : "transform .65s cubic-bezier(.22,1,.36,1)",
          }}
        >
          <button type="button" className="modal__close" onClick={closeWithAnimation} aria-label="Закрыть">
          <Icon name="close" size={18} />
        </button>

        <div className="add-modal">
          <div className="add-modal__handle" aria-hidden="true" />
          <p className="eyebrow">Моя полка</p>
          <h2>{title}</h2>

          {mode === "menu" && (
            <>
              <button type="button" className="add-menu__auto" onClick={() => switchMode("auto")}>
                <span className="add-menu__auto-icon">
                  <Icon name="sparkle" size={22} />
                </span>
                <span>
                  <strong>Автоподбор продукта</strong>
                  <small>Подберём средства под вашу кожу и полку</small>
                </span>
                <Icon name="chevron" size={18} />
              </button>

              <div className="add-menu__grid">
                <button
                  type="button"
                  className="add-menu__opt"
                  onClick={onGoToCatalog}
                >
                  <Icon name="box" size={18} />
                  <span>Из каталога</span>
                </button>
                <button type="button" className="add-menu__opt" onClick={() => onScan("photo")}>
                  <Icon name="camera" size={18} />
                  <span>Скан по фото</span>
                </button>
                <button type="button" className="add-menu__opt" onClick={() => onScan("manual")}>
                  <Icon name="pencil" size={18} />
                  <span>Ручной ввод</span>
                </button>
              </div>
            </>
          )}

          {(mode === "catalog" || mode === "auto") && (
            <>
              <button type="button" className="add-modal__back" onClick={() => switchMode("menu")}>
                <Icon name="back" size={15} />
                Назад
              </button>

              {mode === "catalog" && (
                <div className="search">
                  <Icon name="search" size={16} />
                  <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Название, бренд или актив…"
                  />
                </div>
              )}

              {mode === "auto" && (
                <>
                  <p className="autopick-select-label">
                    Что хотите подобрать?
                  </p>

                  <div className="autopick-category-grid">
                    {FACE_TAXONOMY.filter((c) => c.title !== "Уход за губами")
                      .map((c) => c.title)
                      .map((c, i) => (
                        <button
                          key={c}
                          type="button"
                          className={`autopick-category ${recCat === c ? "autopick-category--active" : ""}`}
                          onClick={() => setRecCat(c)}
                        >
                          <span className="autopick-category__number">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <span className="autopick-category__name">{c}</span>
                          <Icon name="chevron" size={15} />
                        </button>
                      ))}
                  </div>

                  <button
                    type="button"
                    className="autopick-pick-button"
                    disabled={!recCat || recsLoading}
                    onClick={() => {
                      if (!recsLoading && list.length) {
                        onPickReady(list)
                      }
                    }}
                  >
                    {recsLoading ? (
                      <>
                        <span className="spin" />
                        Подбираем…
                      </>
                    ) : (
                      <>
                        Подобрать
                        <Icon name="arrow" size={16} />
                      </>
                    )}
                  </button>
                </>
              )}

              {mode === "catalog" && (
                <div className="add-modal__list">
                  {catLoading ? (
                    <p className="empty">Ищем…</p>
                  ) : list.map((p) => (
                    <div key={p.id} className="rec">
                      <button type="button" className="rec__main" onClick={() => onOpen(p)}>
                        <img src={p.image} alt="" loading="lazy" />
                        <span>
                          <strong>{p.name}</strong>
                          <small>{p.brand} · {p.category}</small>
                        </span>
                      </button>

                      <button
                        type="button"
                        className="add-modal__add"
                        onClick={() => { void Promise.resolve(onAdd(p)).catch(() => {}) }}
                        aria-label="Добавить"
                      >
                        <Icon name="plus" size={16} />
                      </button>
                    </div>
                  ))}

                  {!catLoading && list.length === 0 && (
                    <p className="empty">Ничего не нашлось.</p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
        </div>
      </div>
    </div>
  )
}

function AutoPickResultsOverlay({
  items,
  onClose,
  onAdd,
  onOpen,
}: {
  items: Product[]
  onClose: () => void
  onAdd: (p: Product) => void
  onOpen: (p: Product, card?: HTMLElement) => void
}) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setVisible(true))
    return () => window.cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      className={`autopick-results ${visible ? "autopick-results--visible" : ""}`}
      onClick={onClose}
    >
      <div
        className="autopick-results__backdrop"
        aria-hidden="true"
      />

      <div className="autopick-results__mask" />

      <div className="autopick-results__content" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="autopick-results__close"
          onClick={onClose}
          aria-label="Закрыть подбор"
        >
          <Icon name="close" size={19} />
        </button>

        <div className="autopick-results__heading">
          <h2>Подобрали для вас</h2>
          <div className="autopick-results__swipe" aria-label="Свайпайте карточки">
            <span className="autopick-results__swipe-label autopick-results__swipe-label--skip">← Пропускаем</span>
            <span className="autopick-results__swipe-label autopick-results__swipe-label--add">Добавляем →</span>
          </div>
        </div>

        <AutoPickCarousel
          items={items}
          onOpen={onOpen}
          onAdd={onAdd}
        />
      </div>
    </div>
  )
}


function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="help-modal">
          <p className="eyebrow">айдерми</p>
          <h2>Помощь</h2>
          <p className="help-modal__hint">Есть вопрос или предложение? Напишите нам — ответим в ближайшее время.</p>
          <div className="help-modal__links">
            <a href="https://t.me/aidermy_news" target="_blank" rel="noopener noreferrer" className="help-modal__link">
              <span className="help-modal__icon"><Icon name="send" size={18} /></span>
              <span><strong>Telegram</strong><small>@aidermy_news</small></span>
              <Icon name="chevron" size={16} />
            </a>
            <a href="mailto:lyr.ami.tag@gmail.com" className="help-modal__link">
              <span className="help-modal__icon"><Icon name="mail" size={18} /></span>
              <span><strong>Email</strong><small>lyr.ami.tag@gmail.com</small></span>
              <Icon name="chevron" size={16} />
            </a>
          </div>
          <Button variant="ghost" onClick={onClose} className="w-full">Закрыть</Button>
        </div>
      </div>
    </div>
  )
}

function DeleteAccountModal({ onClose, onDeleted }: { onClose: () => void; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const ready = confirm.trim().toUpperCase() === "УДАЛИТЬ"

  const submit = async () => {
    if (!ready || loading) return
    setLoading(true)
    setError("")
    try {
      await api.deleteAccount(confirm.trim(), password || undefined)
      onDeleted()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось удалить аккаунт")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="auth-modal">
          <p className="eyebrow">Аккаунт</p>
          <h2>Удалить аккаунт</h2>
          <div className="danger-note">
            Будут удалены профиль кожи, история проверок, полка, отчёты, загруженные фото и привязки входа.
            Действие необратимо.
          </div>
          <label className="field">
            <span>Введите слово УДАЛИТЬ</span>
            <input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="УДАЛИТЬ" autoComplete="off" />
          </label>
          <label className="field">
            <span>Пароль (для входа по паролю)</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
          </label>
          {error && <p className="auth-modal__error" role="alert">{error}</p>}
          <Button className="w-full" onClick={submit} disabled={!ready || loading}>
            {loading ? "Удаляем…" : "Удалить аккаунт навсегда"}
          </Button>
          <button type="button" className="guest-link" onClick={onClose}>Отмена</button>
          <p className="panel__note">
            Нет доступа к аккаунту? Напишите на{" "}
            <a href="mailto:aidermy@yandex.com">aidermy@yandex.com</a>.
          </p>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [items, setItems] = useState<Product[]>([])
  const [shelfItems, setShelfItems] = useState<Product[]>([])
  const [removeProduct, setRemoveProduct] = useState<Product | null>(null)
  const [removeReason, setRemoveReason] = useState("")
  const [clearCabinet, setClearCabinet] = useState<CabinetKey | null>(null)
  const [page, setPage] = useState<Page>("home")
  // Прямое открытие /offer, /privacy и т.п. обрабатывается по pathname.
  const [legalPath, setLegalPath] = useState<string | null>(() => legalDocFromPath(window.location.pathname))
  const [open, setOpen] = useState<Product | null>(null)
  const [morphOrigin, setMorphOrigin] = useState<HTMLElement | null>(null)
  const [checkingIds, setCheckingIds] = useState<Set<number>>(new Set())
  const [user, setUser] = useState<User | null>(null)
  // Гостевой сценарий: прогресс живёт ТОЛЬКО в памяти React и не пишется в
  // localStorage/sessionStorage — после перезагрузки гость начинает заново.
  const [guestStage, setGuestStage] = useState<"home" | "quiz" | "select" | "scan" | "result">("home")
  const [guestToken, setGuestToken] = useState("")
  const [guestProduct, setGuestProduct] = useState<Product | null>(null)
  const [guestBusy, setGuestBusy] = useState(false)
  const [guestError, setGuestError] = useState("")
  const [authModal, setAuthModal] = useState<null | "login" | "register">(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [pricingOpen, setPricingOpen] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [autoPickResults, setAutoPickResults] = useState<Product[] | null>(null)
  const [pointsOpen, setPointsOpen] = useState(false)
  const [scanMethod, setScanMethod] = useState<ScanMethod | null>(null)
  const [loading, setLoading] = useState(true)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogCategory, setCatalogCategory] = useState("")
  const [query, setQuery] = useState("")
  const [helpOpen, setHelpOpen] = useState(false)
  const [toast, setToast] = useState("")
  const [shelfLoading, setShelfLoading] = useState(false)
  const [, setProfileVersion] = useState(0)

  useEffect(() => {
    const refreshProfile = () => setProfileVersion((value) => value + 1)
    window.addEventListener("aidermy-profile-updated", refreshProfile)
    return () => window.removeEventListener("aidermy-profile-updated", refreshProfile)
  }, [])
  useEffect(() => { const t = window.setTimeout(() => setLoading(false), 1200); return () => window.clearTimeout(t) }, [])
  useEffect(() => { if (!toast) return; const t = window.setTimeout(() => setToast(""), 2200); return () => window.clearTimeout(t) }, [toast])

  // Восстановление сессии по сохранённому токену (в т.ч. Google OAuth ?token=).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""))
    const authError = params.get("auth_error")
    if (authError) {
      const msg = authError === "yandex_email_taken"
        ? "Аккаунт с таким email уже существует. Войдите по паролю, чтобы затем связать Яндекс."
        : authError === "yandex_cancelled"
          ? "Вход через Яндекс отменён."
          : authError === "yandex_not_configured"
            ? "Вход через Яндекс пока не настроен."
            : "Не удалось войти через Яндекс. Попробуйте ещё раз."
      setToast(msg)
      params.delete("auth_error")
    }
    // Токен приходит во фрагменте (#token=…): фрагмент не отправляется на сервер,
    // поэтому не попадает в логи и Referer. Query-вариант поддержан для совместимости.
    const urlToken = hashParams.get("token") || params.get("token")
    if (urlToken) {
      setToken(urlToken)
      hashParams.delete("token")
      params.delete("token")
    }
    if (authError || urlToken) {
      const restQuery = params.toString()
      const restHash = hashParams.toString()
      window.history.replaceState(
        null,
        "",
        window.location.pathname
          + (restQuery ? "?" + restQuery : "")
          + (restHash ? "#" + restHash : ""),
      )
    }
    const token = getToken()
    if (!token) return
    api.me()
      .then((u) => {
        const displayName = u.name || u.email?.split("@")[0] || "Пользователь"
        const plan: Plan = u.plan === "pro" || u.plan === "plus" ? u.plan : "free"
        setUser({ name: displayName, initials: displayName.slice(0, 2).toUpperCase(), plan, points: u.balance || 0 })
        // Скользящая сессия: продлеваем токен, пока пользователь активен.
        // Если пользователь успел выйти, пока шёл refresh, токен не возвращаем.
        api.refresh().then((r) => { if (getToken()) setToken(r.access_token) }).catch(() => {})
      })
      .catch((err) => {
        // Токен стираем ТОЛЬКО если сервер явно сказал, что сессия недействительна.
        // Сетевой сбой / временный 5xx не должен выкидывать пользователя.
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) setToken(null)
      })
    api.getProfile()
      .then((r) => {
        const p = (r.profile || {}) as { skinType?: string; age?: string; concerns?: string[]; allergies?: string[]; structuredProfile?: unknown }
        if (p.skinType || p.age || p.concerns?.length || p.allergies?.length || p.structuredProfile) {
          const pd = {
            skinType: p.skinType || getUserProfile().skinType,
            age: p.age || getUserProfile().age,
            concerns: p.concerns || [],
            allergies: p.allergies || [],
            structured: p.structuredProfile || null,
          }
          setUserProfile(pd)
        }
      })
      .catch(() => {})
  }, [])

  // Загрузка реальных продуктов из каталога (фолбэк — mock).
  useEffect(() => {
    api.catalog({ limit: 200, sort: "popular" })
      .then((res) => {
        const mapped = (res.products || []).map(mapApiProduct).filter((p) => p.name && p.name !== "Продукт")
        if (mapped.length) setItems(mapped)
      })
      .catch(() => {})
      .finally(() => setCatalogLoading(false))
  }, [])

  // Полка: грузим реальные шкафы и отмечаем продукты как «использую».
  const loadShelf = (): Promise<void> => {
    if (!getToken()) return Promise.resolve()
    setShelfLoading(true)
    return api.shelf()
      .then((res) => {
        const shelfIds = new Set<number>()
        const mapped: Product[] = []
        for (const cab of res.cabinets || []) {
          for (const cat of cab.categories || []) {
            for (const it of cat.items || []) {
              if (it.product_id != null) shelfIds.add(it.product_id)
              mapped.push(mapShelfItem(it))
            }
          }
        }
        setShelfItems(mapped)
        // Полка — источник истины для статуса «использую»: то, что с неё убрали
        // (в другой вкладке/устройстве), не должно оставаться «использую» в UI.
        setItems((cur) => cur.map((p) => (
          shelfIds.has(p.id)
            ? { ...p, state: "using" as ProductState }
            : (p.state === "using" ? { ...p, state: undefined, shelf_id: undefined } : p)
        )))
      })
      .catch(() => {})
      .finally(() => setShelfLoading(false))
  }
  useEffect(() => { loadShelf() }, [])
  // A profile save can make shelf results stale; reload the actual shelf state
  // whenever the user opens it, not only after a full page refresh.
  useEffect(() => {
    if (page === "shelf" && user) void loadShelf()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  // Блокируем прокрутку фона, когда открыт drawer или модалка.
  useEffect(() => {
    const locked =
    open != null ||
    authModal != null ||
    pricingOpen ||
    addModalOpen ||
    autoPickResults != null ||
    pointsOpen ||
    removeProduct != null ||
    clearCabinet != null
    if (locked) {
      const prevBody = document.body.style.overflow
      const prevHtml = document.documentElement.style.overflow
      document.body.style.overflow = "hidden"
      document.documentElement.style.overflow = "hidden"
      return () => { document.body.style.overflow = prevBody; document.documentElement.style.overflow = prevHtml }
    }
  }, [open, authModal, pricingOpen, addModalOpen, autoPickResults, pointsOpen, removeProduct, clearCabinet])

  useEffect(() => {
    const onPop = () => setLegalPath(legalDocFromPath(window.location.pathname))
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])

  const openLegal = (path: string) => {
    const slug = (path || "/").replace(/^\/+/, "").replace(/\/+$/, "")
    if (!slug) {
      window.history.pushState(null, "", "/")
      setLegalPath(null)
      window.scrollTo({ top: 0 })
      return
    }
    window.history.pushState(null, "", `/${slug}`)
    setLegalPath(slug)
    window.scrollTo({ top: 0 })
  }

  const navigate = (p: Page) => {
    // Гостю доступна только «Главная»: остальные разделы требуют входа.
    if (!user && p !== "home") { setAuthModal("login"); return }
    if (p === "sets") { setPage("home"); window.scrollTo({ top: 0 }); return }
    if (p === "shelf" && !user) { setAuthModal("login"); return }
    if (p === "report") { setToast("Раздел «Отчёт» скоро появится"); return }
    if (p === "scan") setScanMethod(null)
    if (p === "catalog") setCatalogCategory("")
    setPage(p)
    window.scrollTo({ top: 0 })
  }

  const onChecking = (id: number) => setCheckingIds((prev) => new Set(prev).add(id))
  const onChecked = (id: number, score: number | null, verdict: Verdict | null, recommendationStatus?: string, analysisId?: number) => {
    // Один и тот же результат проверки должен немедленно отражаться везде,
    // где показан продукт: каталог (items), полка (shelfItems) и открытая карточка (open).
    const applyMatch = (p: Product): Product => (p.id === id
      ? { ...p, match: { ...(p.match ?? { score: null }), score, verdict: verdict ?? p.match?.verdict, recommendation_status: recommendationStatus ?? p.match?.recommendation_status, analysis_id: analysisId ?? p.match?.analysis_id } }
      : p)
    setItems((cur) => cur.map(applyMatch))
    setShelfItems((cur) => cur.map(applyMatch))
    setOpen((o) => (o && o.id === id ? applyMatch(o) : o))
    setCheckingIds((prev) => { const n = new Set(prev); n.delete(id); return n })
  }
  const onCheckFinished = (id: number) => setCheckingIds((prev) => { const n = new Set(prev); n.delete(id); return n })
  const onReported = (id: number, analysisId?: number) => {
    const applyAnalysis = (p: Product): Product => (p.id === id
      ? { ...p, match: p.match ? { ...p.match, analysis_id: analysisId ?? p.match.analysis_id } : undefined }
      : p)
    setItems((cur) => cur.map(applyAnalysis))
    setShelfItems((cur) => cur.map(applyAnalysis))
    setOpen((o) => (o && o.id === id ? applyAnalysis(o) : o))
  }

  const resetGuestFlow = () => {
    setGuestStage("home")
    setGuestToken("")
    setGuestProduct(null)
    setGuestBusy(false)
    setGuestError("")
  }

  const startGuestFlow = () => {
    resetGuestFlow()
    setGuestStage("quiz")
    window.scrollTo({ top: 0 })
  }

  const handleGuestQuizDone = async (p: { skinType: string; age?: string; concerns?: string[]; allergies?: string[]; structured?: Record<string, unknown> }) => {
    const skinTypeLabel = SKIN_TYPE_OPTIONS.find((o) => o.id === p.skinType)?.label ?? p.skinType
    // Профиль остаётся в памяти модуля (не в браузерном хранилище).
    setUserProfile({
      skinType: skinTypeLabel,
      age: p.age ?? "",
      concerns: p.concerns ?? [],
      allergies: p.allergies ?? [],
      structured: p.structured ?? null,
    })
    setGuestBusy(true)
    setGuestError("")
    try {
      const profile = { ...buildProfile(), skin_type: skinTypeLabel }
      const res = await api.guestSession(profile as Record<string, unknown>)
      setGuestToken(res.guest_token)
      setGuestStage("select")
      window.scrollTo({ top: 0 })
    } catch (e) {
      setGuestError(e instanceof Error ? e.message : "Не удалось начать гостевую проверку.")
    } finally {
      setGuestBusy(false)
    }
  }

  const handleGuestPick = async (item: ApiProduct) => {
    if (guestBusy || !guestToken) return
    setGuestBusy(true)
    setGuestError("")
    try {
      const profile = buildProfile()
      const skinType = getUserProfile().skinType
      const base = {
        product_name: item.name || "",
        brand: item.brand || "",
        skin_type: skinType,
        profile,
        guest_token: guestToken,
      }
      const ingredients = (item.ingredients || "").trim()
      const res = ingredients
        ? await api.checkWithIngredients({ ...base, ingredients })
        : await api.check(base)
      if (res.pending) {
        setGuestError("Исследование состава ещё не завершено. Попробуйте это средство позже.")
        return
      }
      const product: Product = {
        ...mapApiProduct(item),
        match: {
          score: typeof res.score === "number" ? res.score : null,
          verdict: mapVerdict(typeof res.score === "number" ? res.score : null, res.verdict) ?? undefined,
          recommendation_status: res.recommendation_status,
          summary: res.summary,
          safe_ingredients: res.safe_ingredients,
          caution_ingredients: res.caution_ingredients,
          analysis_id: res.analysis_id,
          phase1_status: res.phase1_status,
        },
      }
      setGuestProduct(product)
      setGuestStage("result")
      window.scrollTo({ top: 0 })
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 0
      setGuestError(
        status === 409
          ? "Гостевая проверка уже использована. Зарегистрируйтесь, чтобы проверять средства без ограничений."
          : status === 401 || status === 410
            ? "Гостевой сеанс завершён. Начните проверку заново."
            : "Не удалось выполнить проверку. Попробуйте ещё раз.",
      )
    } finally {
      setGuestBusy(false)
    }
  }

  const handleLogin = (u: User) => {
    setUser(u)
    setAuthModal(null)
    void loadShelf()
    // Гость только что прошёл проверку — сохраняем её результат в аккаунт.
    if (guestToken && guestProduct) {
      const token = guestToken
      void api.guestClaim(token)
        .then((r) => {
          setToast(r.already_claimed ? "Результат уже сохранён в аккаунте" : "Результат сохранён в аккаунте")
          return loadShelf()
        })
        .then(() => { setPage("shelf"); window.scrollTo({ top: 0 }) })
        .catch(() => setToast("Не удалось сохранить гостевой результат"))
        .finally(() => resetGuestFlow())
    }
  }
  const handleAccountDeleted = () => {
    setDeleteOpen(false)
    resetGuestFlow()
    setToken(null)
    setUser(null)
    setShelfItems([])
    setItems((cur) => cur.map((p) => ({ ...p, match: undefined, state: undefined, shelf_id: undefined })))
    setPage("home")
    setToast("Аккаунт удалён")
    window.scrollTo({ top: 0 })
  }

  const handleLogout = () => {
    setToken(null)
    setUser(null)
    setShelfItems([])
    setItems((cur) => cur.map((p) => (p.state === "using" ? { ...p, state: undefined, shelf_id: undefined } : p)))
    // Гость видит только главную — после выхода всегда возвращаемся туда.
    setPage("home")
  }
  const handleSelectPlan = async (p: Plan) => {
    if (getToken()) {
      try {
        const r = await api.subscription(p)
        setUser((u) => (u ? { ...u, plan: p, points: r.balance } : u))
        setToast("Тариф обновлён")
      } catch (error) {
        setToast(error instanceof Error ? error.message : "Не удалось изменить тариф")
      }
    } else {
      setUser((u) => (u ? { ...u, plan: p } : u))
    }
  }
  const handleAddToShelf = async (p: Product): Promise<boolean> => {
    const id = p.id
    let shelfId: number | undefined
    let error: string | null = null
    if (!p?.slug) {
      error = "Не удалось добавить: продукт не найден в базе."
    } else if (!getToken()) {
      error = "Войдите в аккаунт, чтобы добавлять на полку."
      setAuthModal("login")
    } else {
      // Полка не требует предварительного AI-check: backend рассчитывает
      // детерминированный score сам. Не запускаем скрытый платный/медленный
      // /check перед сохранением — иначе добавление задерживается и может
      // выглядеть «не сработавшим».
      try {
        const res = await api.addToShelf(p.slug, p.category || "", p.cabinet || "face")
        if (res.status !== "ok" || (res.item?.id == null && !res.duplicate)) {
          throw new Error("Сервер не подтвердил сохранение на полке.")
        }
        shelfId = res.item?.id
      } catch (e) {
        error = e instanceof Error ? e.message : "Не удалось добавить продукт."
      }
    }
    if (error) { setToast(error); throw new Error(error) }
    setItems((cur) => cur.map((x) => (x.id === id ? { ...x, state: "using", shelf_id: shelfId ?? x.shelf_id } : x)))
    // Оптимистично добавляем на полку, чтобы карточка появилась сразу,
    // а затем сверяемся с сервером (он вернёт канонический shelf_id/категорию).
    setShelfItems((cur) => {
      const withoutDup = cur.filter((x) => x.id !== id)
      return [...withoutDup, { ...p, state: "using", shelf_id: shelfId ?? p.shelf_id, cabinet: (p.cabinet || "face") as CabinetKey }]
    })
    setOpen((o) => (o && o.id === id ? { ...o, state: "using", shelf_id: shelfId ?? o.shelf_id } : o))
    setAddModalOpen(false)
    setToast("Добавлено на полку ✓")
    void loadShelf()
    return true
  }
  const handleRemoveFromShelf = async () => {
    const p = removeProduct
    if (getToken()) {
      if (p?.slug && removeReason) { try { await api.removalFeedback(p.slug, removeReason) } catch { /* ignore */ } }
      if (p?.shelf_id) { try { await api.removeFromShelf(p.shelf_id) } catch { /* ignore */ } }
    }
    setItems((cur) => cur.map((x) => (x.id === p?.id ? { ...x, state: undefined, shelf_id: undefined } : x)))
    if (p?.id != null) setShelfItems((cur) => cur.filter((x) => x.id !== p.id))
    setRemoveProduct(null)
    setRemoveReason("")
    loadShelf()
  }
  const handleClearShelf = async () => {
    if (clearCabinet && getToken()) {
      try { await api.clearShelf(clearCabinet) } catch { /* ignore */ }
    }
    // Мгновенно убираем с полки локально, не дожидаясь перезагрузки.
    setShelfItems((cur) => cur.filter((p) => p.cabinet !== clearCabinet))
    setItems((cur) => cur.map((p) => (p.cabinet === clearCabinet ? { ...p, state: undefined, shelf_id: undefined } : p)))
    setClearCabinet(null)
    loadShelf()
  }
  const handleDeleteBatch = async (ids: number[]) => {
    if (ids.length && getToken()) {
      try { await api.deleteBatch(ids) } catch { /* ignore */ }
    }
    setItems((cur) => cur.map((x) => (ids.includes(x.shelf_id ?? -1) ? { ...x, state: undefined, shelf_id: undefined } : x)))
    setShelfItems((cur) => cur.filter((x) => !ids.includes(x.shelf_id ?? -1)))
    void loadShelf()
  }
  const handleCategoryEdit = async (shelfId: number, category: string) => {
    if (shelfId && getToken()) {
      try { await api.updateShelfCategory(shelfId, category) } catch { /* ignore */ }
    }
    setShelfItems((cur) => cur.map((x) => (x.shelf_id === shelfId ? { ...x, category, tags: category ? [category] : [] } : x)))
    void loadShelf()
  }
  const handleTopUp = async (amount: number) => {
    if (getToken()) {
      try {
        const r = await api.topUp(amount)
        setUser((u) => (u ? { ...u, points: r.balance } : u))
        setToast("Баллы добавлены")
      } catch (error) {
        setToast(error instanceof Error ? error.message : "Не удалось пополнить баланс")
      }
    } else {
      setUser((u) => (u ? { ...u, points: u.points + amount } : u))
    }
  }
  const handleScanFromAdd = (m: ScanMethod) => {
    setAddModalOpen(false)
    setScanMethod(m)
    setPage("scan")
    window.scrollTo({ top: 0 })
  }
  const goToCatalog = (q: string, category = "") => {
    // Открытая карточка должна закрыться, а каталог — открыться уже с фильтром.
    setOpen(null)
    setMorphOrigin(null)
    setQuery(q)
    setCatalogCategory(category)
    setPage("catalog")
    window.scrollTo({ top: 0 })
  }

  if (legalPath) {
    return <LegalPage slug={legalPath} onNavigate={openLegal} />
  }

  return (
    <div className={`app-shell ${user ? "" : "app-shell--guest"}`}>
      <LoadingScreen done={!loading} />
      {user && <Sidebar page={page} onNavigate={navigate} user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onPoints={() => setPointsOpen(true)} />}
      <div className="workspace">
        {user && <Topbar page={page} onNavigate={navigate} onHelp={() => setHelpOpen(true)} user={user} onAuth={() => setAuthModal("login")} onPoints={() => setPointsOpen(true)} />}
        {user && <GlobalBar query={query} onQuery={setQuery} user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onPoints={() => setPointsOpen(true)} onLogout={handleLogout} onNavigate={navigate} onOpen={setOpen} onHelp={() => setHelpOpen(true)} />}
        <main className="main-content">
          <div key={user ? page : `guest-${guestStage}`} className="page-anim">
            {user && page === "home" && <HomePage onNavigate={navigate} onOpen={setOpen} onScan={() => navigate("scan")} user={user} items={items} shelfItems={shelfItems} />}
            {!user && guestStage === "home" && (
              <GuestHomePage onAuth={() => setAuthModal("login")} onStart={startGuestFlow} />
            )}
            {!user && guestStage === "quiz" && (
              <GuestQuizScreen onDone={handleGuestQuizDone} onBack={resetGuestFlow} />
            )}
            {!user && guestStage === "select" && (
              <GuestSelectScreen
                onPick={handleGuestPick}
                onScan={() => setGuestStage("scan")}
                busy={guestBusy}
                error={guestError}
              />
            )}
            {!user && guestStage === "scan" && (
              <div className="guest-scan">
                <button type="button" className="guest-link" onClick={() => setGuestStage("select")}>← К выбору средства</button>
                <ScanPage
                  guestToken={guestToken}
                  onContinue={(p) => { setGuestProduct(p); setGuestStage("result"); window.scrollTo({ top: 0 }) }}
                />
              </div>
            )}
            {!user && guestStage === "result" && guestProduct && (
              <GuestResultScreen
                product={guestProduct}
                guestToken={guestToken}
                onSignup={() => setAuthModal("register")}
                onLogin={() => setAuthModal("login")}
                onRestart={resetGuestFlow}
              />
            )}
            {user && page === "shelf" && <ShelfPage items={shelfItems.length ? shelfItems : items} loading={shelfLoading} limit={PLANS.find((p) => p.key === user.plan)?.shelfLimit ?? 5} checkingIds={checkingIds} onOpen={setOpen} onAdd={() => setAddModalOpen(true)} onRemove={(p) => setRemoveProduct(p)} onClear={(c) => setClearCabinet(c)} onDeleteBatch={handleDeleteBatch} onRefresh={() => void loadShelf()} onBalance={(balance) => setUser((u) => (u ? { ...u, points: balance } : u))} />}
            {user && page === "sets" && <CareSetsPage user={user} onAuth={() => setAuthModal("login")} />}
            {user && page === "scan" && <ScanPage onContinue={setOpen} initialMethod={scanMethod ?? undefined} />}
            {user && page === "catalog" && <CatalogPage items={items} checkingIds={checkingIds} onOpen={setOpen} query={query} onQuery={setQuery} initialCategory={catalogCategory} loading={catalogLoading} />}
            {user && page === "profile" && <ProfilePage user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onLogout={handleLogout} onPoints={() => setPointsOpen(true)} onDelete={() => setDeleteOpen(true)} />}
          </div>
        </main>
        <SiteFooter onNavigate={openLegal} />
      </div>
      {user && <BottomNav page={page} onNavigate={navigate} />}
      {open && <ProductDrawer key={open.id} product={open} morphOrigin={morphOrigin} user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onClose={() => setOpen(null)} onChecking={onChecking} onChecked={onChecked} onCheckFinished={onCheckFinished} onReported={onReported} onOpen={setOpen} onGoToCatalog={goToCatalog} onAddToShelf={handleAddToShelf} onRemove={(p) => setRemoveProduct(p)} onCategoryEdit={handleCategoryEdit} />}
      {authModal && <AuthModal mode={authModal} onClose={() => setAuthModal(null)} onSuccess={handleLogin} onSwitch={setAuthModal} />}
      {pricingOpen && <PricingModal user={user} onClose={() => setPricingOpen(false)} onSelectPlan={handleSelectPlan} />}
      {deleteOpen && <DeleteAccountModal onClose={() => setDeleteOpen(false)} onDeleted={handleAccountDeleted} />}
      {pointsOpen && <PointsModal user={user} onClose={() => setPointsOpen(false)} onTopUp={handleTopUp} />}
      {addModalOpen && (
        <ShelfAddModal
          items={items}
          onClose={() => setAddModalOpen(false)}
          onAdd={handleAddToShelf}
          onScan={handleScanFromAdd}
          onOpen={(p) => {
            setAddModalOpen(false)
            setOpen(p)
          }}
          onPickReady={(products) => {
            setAddModalOpen(false)
            setAutoPickResults(products)
          }}
          onGoToCatalog={() => {
            setAddModalOpen(false)
            navigate("catalog")
          }}
        />
      )}

      {autoPickResults && (
        <AutoPickResultsOverlay
          items={autoPickResults}
          onClose={() => setAutoPickResults(null)}
          onAdd={handleAddToShelf}
          onOpen={(p, card) => {
            setMorphOrigin(card ?? null)
            setOpen(p)
          }}
        />
      )}
      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
      {removeProduct && (
        <div className="modal-backdrop" onClick={() => setRemoveProduct(null)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal__close" onClick={() => setRemoveProduct(null)} aria-label="Закрыть"><Icon name="close" size={18} /></button>
            <div className="auth-modal">
              <p className="eyebrow">Моя полка</p>
              <h2>Убрать продукт?</h2>
              <p className="auth-modal__hint">{removeProduct.brand} · {removeProduct.name}. Почему убираете?</p>
              <div className="remove-reasons">
                {["Не подошёл", "Вызвал реакцию", "Хочу попробовать новое", "Другое"].map((r) => (
                  <button key={r} type="button" className={`chip ${removeReason === r ? "chip--on" : ""}`} onClick={() => setRemoveReason(r)}>{r}</button>
                ))}
              </div>
              <Button className="w-full" onClick={handleRemoveFromShelf}>Убрать с полки</Button>
              <Button variant="ghost" onClick={() => setRemoveProduct(null)} className="w-full">Отмена</Button>
            </div>
          </div>
        </div>
      )}
      {clearCabinet && (
        <div className="modal-backdrop" onClick={() => setClearCabinet(null)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal__close" onClick={() => setClearCabinet(null)} aria-label="Закрыть"><Icon name="close" size={18} /></button>
            <div className="auth-modal">
              <p className="eyebrow">Моя полка</p>
              <h2>Очистить полку?</h2>
              <p className="auth-modal__hint">Все продукты из текущего шкафа будут удалены с полки.</p>
              <Button className="w-full" onClick={handleClearShelf}>Очистить</Button>
              <Button variant="ghost" onClick={() => setClearCabinet(null)} className="w-full">Отмена</Button>
            </div>
          </div>
        </div>
      )}
      {toast && <div className="toast" role="status" aria-live="polite">{toast}</div>}
    </div>
  )
}
