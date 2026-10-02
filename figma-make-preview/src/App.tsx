import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import loadingGif from "./assets/loading.gif"
import { api, setToken, getToken } from "./api"
import { mapApiProduct, mapShelfItem, buildProfile } from "./mapping"
import {
  products, skinProfile, shelfReport, CABINETS, PLANS, SUBSCRIPTION_ROWS, EXTRA_POINTS_NOTE,
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
  | "link" | "pencil" | "coins" | "crown" | "logout" | "lock" | "send" | "mail"

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
  if (verdict === "Подходит") return "good"
  if (verdict === "Осторожно") return "warn"
  if (verdict === "Не подходит") return "bad"
  if (score == null) return "neutral"
  return score >= 80 ? "good" : score >= 60 ? "warn" : "bad"
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

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return null
  return <span className={`score-badge score-badge--${toneOf(score, null)}`}>{score}%</span>
}

function Avatar({ size = 34, initials = skinProfile.initials }: { size?: number; initials?: string }) {
  return <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.4 }}>{initials}</span>
}

function ScoreRing({ score, label = "совместимость" }: { score: number; label?: string }) {
  const size = 148, stroke = 8, r = (size - stroke) / 2, c = 2 * Math.PI * r
  const [progress, setProgress] = useState(0)
  useEffect(() => { const id = requestAnimationFrame(() => setProgress(score)); return () => cancelAnimationFrame(id) }, [score])
  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="score-ring__svg">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" className="score-ring__track" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" className={`score-ring__val score-ring__val--${toneOf(score, null)}`} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c - (progress / 100) * c} style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.16,1,.3,1)" }} />
      </svg>
      <div className="score-ring__center"><strong>{progress}%</strong><span>{label}</span></div>
    </div>
  )
}
function ProductName({ name }: { name: string }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const textRef = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const w = wrapRef.current, t = textRef.current
    if (!w || !t) return
    const diff = t.scrollWidth - w.clientWidth
    w.style.setProperty("--marquee-dist", `${-diff}px`)
    w.classList.toggle("pcard__name-wrap--marquee", diff > 0)
  }, [name])
  return (
    <div className="pcard__name-wrap" ref={wrapRef}>
      <span className="pcard__name" ref={textRef}>{name}</span>
    </div>
  )
}

function ProductCard({ product, checking = false, onOpen }: {
  product: Product; checking?: boolean; onOpen?: () => void
}) {
  const checked = product.checked === true && product.score != null
  return (
    <article className="pcard">
      <button type="button" className="pcard__main" onClick={onOpen} aria-label={product.name}>
        <div className="pcard__img">
          <img src={product.image} alt="" loading="lazy" />
          <ScoreBadge score={product.score} />
          {product.state && <span className={`pcard__state pcard__state--${product.state}`} />}
        </div>
        <div className="pcard__body">
          <p className="pcard__brand">{product.brand}</p>
          <ProductName name={product.name} />
          <p className="pcard__cat">{product.category}</p>
        </div>
      </button>
      <div className="pcard__foot">
        {!checked && (checking ? (
          <span className="pcard__checking"><span className="spin" /> Проверяем…</span>
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
  { id: "report", icon: "chart", label: "Отчёт" },
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
          <span className="sidebar-card__icon"><Icon name="coins" /></span>
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
        <span><strong>{user?.name ?? "Гость"}</strong><small>{user ? skinProfile.skinType : "Тип кожи не задан"}</small></span>
        <Icon name="chevron" size={15} />
      </button>
    </aside>
  )
}

function GlobalBar({ query, onQuery, user, onAuth, onPricing, onPoints, onLogout, onNavigate, onOpen, onHelp }: {
  query: string; onQuery: (v: string) => void; user: User | null; onAuth: () => void; onPricing: () => void; onPoints: () => void; onLogout: () => void; onNavigate: (p: Page) => void; onOpen: (p: Product) => void; onHelp: () => void
}) {
  const [focused, setFocused] = useState(false)
  const needle = query.trim().toLowerCase()
  const matches = needle ? products.filter((p) => [p.name, p.brand, p.category, ...p.tags].join(" ").toLowerCase().includes(needle)).slice(0, 6) : []
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
            <button type="button" className="points-chip" onClick={onPoints}><Icon name="coins" size={16} /><strong>{user.points}</strong><span>баллов · {PLANS.find((p) => p.key === user.plan)?.title}</span></button>
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
          <button type="button" className="topbar__points" onClick={onPoints} aria-label="Пополнить баллы"><Icon name="coins" size={15} /><strong>{user.points}</strong></button>
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
function HomePage({ onNavigate, onOpen, onScan, user }: {
  onNavigate: (p: Page) => void; onOpen: (p: Product) => void; onScan: () => void; user: User | null
}) {
  const using = products.filter((p) => p.state === "using").slice(0, 4)
  const recent = products.filter((p) => p.checked).slice(0, 6)
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
        <section className="panel panel--click" onClick={() => onNavigate("report")}>
          <p className="eyebrow">Моя полка · сводка</p>
          <div className="report-preview">
            <div className="report-preview__num"><strong>{shelfReport.average}</strong><span>%</span></div>
            <p className="report-preview__label">средняя совместимость полки</p>
          </div>
        </section>

        <section className="panel">
          <p className="eyebrow">Профиль кожи</p>
          <h3 className="panel__h3">{skinProfile.skinType}</h3>
          <div className="chips">
            {skinProfile.goals.map((g) => <span key={g} className="chip">{g}</span>)}
            <span className="chip chip--warn">чувствительная</span>
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
          {products.filter((p) => p.state === "want").slice(0, 3).map((p) => (
            <button key={p.id} type="button" className="rec" onClick={() => onOpen(p)}>
              <img src={p.image} alt="" loading="lazy" />
              <span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>
              {p.score != null && <ScoreBadge score={p.score} />}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
function ShelfPage({ items, checkingIds, onOpen, onAdd }: {
  items: Product[]; checkingIds: Set<number>; onOpen: (p: Product) => void; onAdd: () => void
}) {
  const [active, setActive] = useState<CabinetKey>("face")
  const wrapRef = useRef<HTMLDivElement>(null)
  const [cardsPerShelf, setCardsPerShelf] = useState(5)

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
  }, [active])

  const cabinet = CABINETS.find((c) => c.key === active) ?? CABINETS[0]
  const shelved = items.filter((p) => p.state && p.cabinet === active)

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
    const scored = shelved.filter((p) => p.score != null)
    return scored.length ? Math.round(scored.reduce((s, p) => s + (p.score ?? 0), 0) / scored.length) : null
  })()
  const shelfVerdict = avg == null ? "—" : avg >= 80 ? "Отлично" : avg >= 60 ? "Осторожно" : "Конфликт"

  return (
    <div className="page">
      <PageHeading eyebrow="Уход" title="Моя полка" lead="Шкафы по зонам ухода. Полка сама раскладывается под ширину экрана — категории обводятся пунктиром."
        action={<Button icon="plus" onClick={onAdd}>Добавить средство</Button>} />

      <div className="cabinet-tabs">
        {CABINETS.map((c) => {
          const count = items.filter((p) => p.state && p.cabinet === c.key).length
          return (
            <button key={c.key} type="button" className={`cabinet-tab ${active === c.key ? "cabinet-tab--active" : ""}`} onClick={() => setActive(c.key)}>
              {c.short}<span>{count}</span>
            </button>
          )
        })}
      </div>

      <div key={active} className="shelf-anim">
        <div className="shelf-summary">
          <div><strong>{shelved.length}</strong><span>средств на полке</span></div>
          <div><strong>{avg != null ? `${avg}%` : "—"}</strong><span>средняя совместимость</span></div>
          <div><strong>{shelfVerdict}</strong><span>как сочетаются средства</span></div>
        </div>

        <div className="shelf-rack-wrap" ref={wrapRef}>
          {groupedShelves.map((shelf, si) => (
            <div className="shelf" key={si}>
              <div className="shelf__row">
                {shelf.map((group, gi) => (
                  <div className="shelf__group" key={gi}>
                    <span className="shelf__group-label">{group.cat}</span>
                    <div className="shelf__group-cards">
                      {group.cells.map((c) => <ProductCard key={c.product.id} product={c.product} checking={checkingIds.has(c.product.id)} onOpen={() => onOpen(c.product)} />)}
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
          {shelved.length === 0 && <p className="empty">Полка пуста. Добавьте первое средство.</p>}
        </div>
      </div>
      <button type="button" className="shelf-fab" onClick={onAdd} aria-label="Добавить продукт"><Icon name="plus" size={24} /></button>
    </div>
  )
}
function CatalogPage({ items, checkingIds, onOpen, query, onQuery }: {
  items: Product[]; checkingIds: Set<number>; onOpen: (p: Product) => void; query: string; onQuery: (v: string) => void
}) {
  const [cabinet, setCabinet] = useState<"all" | CabinetKey>("all")
  const [cat, setCat] = useState<string>("Все")
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 400)
    window.addEventListener("scroll", onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener("scroll", onScroll)
  }, [])
  const activeCab = CABINETS.find((c) => c.key === cabinet) ?? null
  const cats = activeCab ? ["Все", ...activeCab.categories] : ["Все"]
  const list = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return items.filter((p) => {
      if (cabinet !== "all" && p.cabinet !== cabinet) return false
      if (cat !== "Все" && p.category !== cat) return false
      if (!needle) return true
      return [p.name, p.brand, p.category, ...p.tags].join(" ").toLowerCase().includes(needle)
    })
  }, [items, query, cabinet, cat])

  useEffect(() => { setCat("Все") }, [cabinet])

  return (
    <div className="page">
      <PageHeading eyebrow="База продуктов" title="Каталог" lead="Проверяйте составы и находите продукты под особенности вашей кожи." />
      <div className="search">
        <Icon name="search" size={18} />
        <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Название, бренд или актив…" />
        {query && <button type="button" onClick={() => onQuery("")} className="search__clear" aria-label="Очистить"><Icon name="close" size={15} /></button>}
      </div>
      <div className="tabs">
        <button type="button" className={`tab ${cabinet === "all" ? "tab--active" : ""}`} onClick={() => setCabinet("all")}>Все</button>
        {CABINETS.map((c) => (
          <button key={c.key} type="button" className={`tab ${cabinet === c.key ? "tab--active" : ""}`} onClick={() => setCabinet(c.key)}>{c.short}</button>
        ))}
      </div>
      <div className="tabs tabs--cats">
        {cats.map((c) => (
          <button key={c} type="button" className={`tab ${cat === c ? "tab--active" : ""}`} onClick={() => setCat(c)}>{c}</button>
        ))}
      </div>
      <div className="product-grid">
        {list.map((p) => (
          <ProductCard key={p.id} product={p} checking={checkingIds.has(p.id)} onOpen={() => onOpen(p)} />
        ))}
      </div>
      {list.length === 0 && <p className="empty">Ничего не нашлось. Попробуйте другой запрос.</p>}
      {scrolled && (
        <button type="button" className="to-top" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} aria-label="Наверх"><Icon name="chevron" size={18} /></button>
      )}
    </div>
  )
}
type ScanMethod = "photo" | "inci" | "link" | "manual"

function ScanPage({ onContinue, initialMethod }: { onContinue: (p: Product) => void; initialMethod?: ScanMethod }) {
  const [method, setMethod] = useState<ScanMethod>(initialMethod ?? "photo")
  const [phase, setPhase] = useState<"input" | "recognizing" | "ready">("input")
  const [picked, setPicked] = useState(false)
  const [brand, setBrand] = useState("")
  const [name, setName] = useState("")
  const [inci, setInci] = useState("")
  const [url, setUrl] = useState("")
  const [photoAdded, setPhotoAdded] = useState(false)
  const [inciPhotoAdded, setInciPhotoAdded] = useState(false)
  const [result, setResult] = useState<Product | null>(null)

  const METHODS: { id: ScanMethod; title: string; desc: string; icon: IconName }[] = [
    { id: "photo", title: "Скан по фото упаковки", desc: "Распознаём продукт по фото этикетки", icon: "camera" },
    { id: "inci", title: "Скан по составу", desc: "Фото списка состава (INCI)", icon: "drop" },
    { id: "link", title: "Вставить ссылку", desc: "Вставить ссылку на продукт", icon: "link" },
    { id: "manual", title: "Ручной ввод", desc: "Название, бренд и состав вручную", icon: "pencil" },
  ]

  const needManualFields = method === "inci" || method === "manual"
  const canRun = method === "photo" ? photoAdded : method === "inci" ? brand.trim().length > 0 && name.trim().length > 0 && inciPhotoAdded : method === "link" ? url.trim().length > 0 : brand.trim().length > 0 && name.trim().length > 0 && inci.trim().length > 0

  const run = async () => {
    if (!canRun) return
    setPhase("recognizing")
    if (method === "link") {
      try {
        const res = await api.importUrl(url.trim())
        const prod = res.product || {}
        const base = products[6]
        const p: Product = { ...base, id: prod.id ?? 900 + Math.floor(Math.random() * 90), brand: prod.brand || "Продукт", name: prod.name || "Продукт", image: prod.image_url || base.image, category: prod.category || base.category, checked: false, report: false, score: null, verdict: null, state: "want", slug: prod.slug }
        setBrand(prod.brand || "")
        setName(prod.name || "")
        setInci(prod.ingredients_raw || "")
        setResult(p)
        setPhase("ready")
      } catch {
        const base = products[6]
        const p: Product = { ...base, id: 900 + Math.floor(Math.random() * 90), brand: brand.trim() || base.brand, name: name.trim() || base.name, image: base.image, checked: false, report: false, score: null, verdict: null, state: "want" }
        setResult(p)
        setPhase("ready")
      }
      return
    }
    window.setTimeout(() => {
      const base = products.find((p) => p.brand.toLowerCase() === brand.trim().toLowerCase()) ?? products[6]
      const p: Product = { ...base, id: 900 + Math.floor(Math.random() * 90), brand: brand.trim() || base.brand, name: name.trim() || base.name, image: base.image, checked: false, report: false, score: null, verdict: null, state: "want" }
      setResult(p)
      setPhase("ready")
    }, 1400)
  }

  const fileRef = useRef<HTMLInputElement>(null)
  const readFileAsDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error("read error"))
    reader.readAsDataURL(file)
  })
  const pickPhoto = () => fileRef.current?.click()

  const takePhoto = async (file: File) => {
    setPhotoAdded(true)
    try {
      const dataUrl = await readFileAsDataUrl(file)
      const res = (await api.identify({ images: [dataUrl] })) as { identified?: { brand?: string; product_name?: string; name?: string }; product?: { name?: string; brand?: string } }
      const ident = res.identified || {}
      setBrand(ident.brand || res.product?.brand || "COSRX")
      setName(ident.product_name || ident.name || res.product?.name || "Advanced Snail 96 Mucin Power Essence")
    } catch {
      setBrand("COSRX")
      setName("Advanced Snail 96 Mucin Power Essence")
    }
  }

  const takeInciPhoto = async (file: File) => {
    setInciPhotoAdded(true)
    try {
      const dataUrl = await readFileAsDataUrl(file)
      const res = (await api.compositionRecognize({ images: [dataUrl] })) as { normalized_ingredients?: string[] }
      const ingr = res.normalized_ingredients || []
      setInci(ingr.length ? ingr.join(", ") : "Aqua, Glycerin, Butylene Glycol, Sodium Hyaluronate, Niacinamide, Panthenol, Allantoin, Carbomer, Phenoxyethanol.")
    } catch {
      setInci("Aqua, Glycerin, Butylene Glycol, Sodium Hyaluronate, Niacinamide, Panthenol, Allantoin, Carbomer, Phenoxyethanol.")
    }
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
            <label className="scan-form__area"><span>Ссылка на продукт *</span><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></label>
          )}
          {method === "manual" && (
            <label className="scan-form__area"><span>Состав (INCI) *</span><textarea value={inci} onChange={(e) => setInci(e.target.value)} placeholder="Вставьте полный состав…" rows={5} /></label>
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
              {result.verdict && <VerdictPill verdict={result.verdict} score={result.score} />}
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
          <ul className="obs obs--warn">{shelfReport.attention.map((g) => <li key={g}><Icon name="alert" size={15} /><span>{g}</span></li>)}</ul>
        </section>
      </div>
      <section className="block">
        <SectionHead eyebrow="Дальше" title="Проверьте ещё" />
        <div className="rec-list">
          {want.map((p) => (
            <button key={p.id} type="button" className="rec" onClick={() => onOpen(p)}>
              <img src={p.image} alt="" loading="lazy" />
              <span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>
              {p.score != null && <ScoreBadge score={p.score} />}
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
function Questionnaire({ onDone }: { onDone: (p: { skinType: string }) => void }) {
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
                {on && (
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
          <Button icon="check" onClick={() => onDone({ skinType: skinType ?? "Нормальная" })}>Сохранить профиль</Button>
        ) : (
          <Button disabled={!canNext} onClick={next}>Далее <Icon name="arrow" size={15} /></Button>
        )}
      </div>
    </div>
  )
}
function ProfilePage({ user, onAuth, onPricing, onLogout, onPoints }: {
  user: User | null; onAuth: () => void; onPricing: () => void; onLogout: () => void; onPoints: () => void
}) {
  const [quiz, setQuiz] = useState(false)
  const [skinType, setSkinType] = useState(skinProfile.skinType)
  if (quiz) {
    return (
      <div className="page">
        <PageHeading eyebrow="Профиль" title="Опрос кожи" lead="Несколько шагов — и профиль станет точнее." />
        <Questionnaire onDone={(p) => { setSkinType(SKIN_TYPE_OPTIONS.find((o) => o.id === p.skinType)?.label ?? p.skinType); setQuiz(false) }} />
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
  return (
    <div className="page">
      <PageHeading eyebrow="Профиль" title="Профиль кожи" lead="На основе профиля рассчитывается совместимость каждого продукта."
        action={<div className="page-head__actions"><Button icon="user" onClick={() => setQuiz(true)}>Перепройти опрос</Button><Button variant="ghost" icon="logout" onClick={onLogout}>Выйти</Button></div>} />
      <div className="account-bar">
        <div><p className="eyebrow">Аккаунт</p><strong>{user.name}</strong><span>{user.points} баллов · тариф {plan?.title}</span></div>
        <div className="account-bar__actions">
          <Button variant="secondary" icon="coins" onClick={onPoints}>Пополнить баллы</Button>
          <Button variant="ghost" icon="crown" onClick={onPricing}>Управлять подпиской</Button>
        </div>
      </div>
      <div className="profile-grid">
        <section className="panel"><p className="eyebrow">Тип кожи</p><h3 className="panel__h3">{skinType}</h3><div className="chips">{skinProfile.goals.map((g) => <span key={g} className="chip">{g}</span>)}</div></section>
        <section className="panel"><p className="eyebrow">Чувствительность</p><h3 className="panel__h3">{skinProfile.sensitivity}</h3><p className="panel__note">Избегает: {skinProfile.avoid.join(", ")}</p></section>
        <section className="panel"><p className="eyebrow">Активное лечение</p><ul className="kv">{skinProfile.therapy.map((t) => <li key={t}>{t}</li>)}</ul></section>
        <section className="panel"><p className="eyebrow">Непереносимости</p><div className="chips">{skinProfile.intolerances.map((t) => <span key={t} className="chip chip--warn">{t}</span>)}</div></section>
      </div>
      <section className="block"><p className="profile-note">Match каждого продукта рассчитывается по этому профилю и вашей текущей полке. Реальная математика живёт в scoring engine V1 — здесь показан результат для preview.</p></section>
    </div>
  )
}
function ProductDrawer({ product, user, onAuth, onPricing, onClose, onChecking, onChecked, onReported, onOpen, onGoToCatalog }: {
  product: Product; user: User | null; onAuth: () => void; onPricing: () => void; onClose: () => void;
  onChecking: (id: number) => void; onChecked: (id: number, score: number, verdict: Verdict) => void; onReported: (id: number) => void; onOpen: (p: Product) => void; onGoToCatalog: (q: string) => void
}) {
  const [phase, setPhase] = useState<"idle" | "checking" | "match" | "generating" | "report">(
    product.checked && product.report ? "report" : product.checked ? "match" : "idle"
  )
  const [score, setScore] = useState<number | null>(product.score)
  const [verdict, setVerdict] = useState<Verdict | null>(product.verdict)
  const [closing, setClosing] = useState(false)
  const [rating, setRating] = useState(0)
  const [review, setReview] = useState("")
  const [anonymous, setAnonymous] = useState(false)
  const [sent, setSent] = useState(false)
  const [safeList, setSafeList] = useState<string[]>([])
  const [cautionList, setCautionList] = useState<string[]>([])
  const [reportText, setReportText] = useState("")

  const close = () => { setClosing(true); window.setTimeout(onClose, 200) }
  const submitReview = async () => {
    if (rating <= 0) return
    if (product.slug) {
      try { await api.addReview(product.slug, rating, review, anonymous) } catch { /* ignore */ }
    }
    setSent(true)
  }

  useEffect(() => {
    if (product.slug) api.reviews(product.slug).catch(() => {})
  }, [product.slug])

  const check = async () => {
    setPhase("checking")
    onChecking(product.id)
    const inci = "Aqua, Glycerin, Butylene Glycol, Sodium Hyaluronate, Niacinamide, Panthenol, Allantoin, Carbomer, Phenoxyethanol."
    try {
      const res = await api.checkWithIngredients({
        product_name: product.name,
        skin_type: skinProfile.skinType,
        profile: buildProfile(),
        ingredients: inci,
      })
      const s = res.score ?? 60
      const v: Verdict = res.verdict === "Подходит" ? "Подходит" : res.verdict === "Не подходит" ? "Не подходит" : "Осторожно"
      setScore(s); setVerdict(v); setSafeList(res.safe_ingredients || []); setCautionList(res.caution_ingredients || []); setPhase("match")
      onChecked(product.id, s, v)
    } catch {
      const s = 60 + ((product.id * 13) % 35)
      const v: Verdict = s >= 80 ? "Подходит" : s >= 60 ? "Осторожно" : "Не подходит"
      setScore(s); setVerdict(v); setPhase("match")
      onChecked(product.id, s, v)
    }
  }

  const showReport = async () => {
    if (!user) { onAuth(); return }
    if (user.plan === "free") { onPricing(); return }
    setPhase("generating")
    if (product.slug) {
      try { const res = await api.analysisReport(product.slug); setReportText(res.review || "") } catch { setReportText("") }
    }
    setPhase("report")
    onReported(product.id)
  }

  const safe = safeList.length ? safeList : (product.tags.length ? product.tags.map((t) => `${t} — совместимо с профилем`) : ["Базовый состав без явных конфликтов"])
  const caution = cautionList.length ? cautionList : (verdict === "Не подходит" ? ["Содержит активы, агрессивные для чувствительной кожи", "Конфликт с текущим ретиноидом"] : verdict === "Осторожно" ? ["Возможна реакция при сочетании с ретиноидом", "Начинайте с низкой частоты"] : ["Явных противопоказаний не найдено"])
  const actives = [
    { name: "Гиалуроновая кислота", conc: "средняя", effect: "удерживает влагу" },
    { name: "Ниацинамид", conc: "низкая", effect: "выравнивает тон" },
    { name: "Пантенол", conc: "средняя", effect: "успокаивает" },
  ]
  const similar = products.filter((p) => p.category === product.category && p.id !== product.id).slice(0, 3)

  return (
    <>
      <div className={`drawer-backdrop ${closing ? "drawer-backdrop--closing" : ""}`} onClick={close} />
      <aside className={`drawer ${closing ? "drawer--closing" : ""}`} role="dialog" aria-modal="true">
        <button type="button" className="drawer__close" onClick={close} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="drawer__scroll">
          <div className="drawer__hero">
            <img src={product.image} alt="" />
            <div className="drawer__hero-meta">
              <button type="button" className="drawer__brand-link" onClick={() => onGoToCatalog(product.brand)}>{product.brand}</button>
              <h2>{product.name}</h2>
              <button type="button" className="drawer__cat drawer__cat--link" onClick={() => onGoToCatalog(product.category)}>{product.category}</button>
            </div>
          </div>

          {phase === "idle" && (
            <div className="drawer__body">
              <p className="drawer__note">Состав (INCI)</p>
              <p className="inci">Aqua, Glycerin, Butylene Glycol, Sodium Hyaluronate, Niacinamide, Panthenol, Allantoin, Carbomer, Phenoxyethanol.</p>
              <div className="drawer__cta"><Button icon="sparkle" className="w-full" onClick={check}>Проверить совместимость</Button></div>
            </div>
          )}

          {phase === "checking" && (
            <div className="drawer__body drawer__body--center">
              <span className="spin spin--lg" />
              <h3>Проверяем совместимость…</h3>
              <p>Сопоставляем состав с вашим профилем кожи и текущей полкой.</p>
            </div>
          )}

          {phase === "match" && (
            <div className="drawer__body">
              <div className="drawer__score">
                {score != null && <ScoreRing score={score} label="совместимость" />}
                <div><VerdictPill verdict={verdict} score={score} /><p className="drawer__score-note">Детерминированная проверка состава относительно вашего профиля.</p></div>
              </div>
              <section><h4>Что хорошо</h4><ul className="obs">{safe.map((s) => <li key={s}><Icon name="check" size={15} /><span>{s}</span></li>)}</ul></section>
              <section><h4>На что обратить внимание</h4><ul className="obs obs--warn">{caution.map((s) => <li key={s}><Icon name="alert" size={15} /><span>{s}</span></li>)}</ul></section>
              <div className="drawer__cta">
                {!user ? (
                  <Button icon="lock" className="w-full" onClick={showReport}>Показать отчёт — войдите</Button>
                ) : (
                  <Button icon="file" className="w-full" onClick={showReport}>Показать отчёт</Button>
                )}
              </div>
            </div>
          )}

          {phase === "generating" && (
            <div className="drawer__body drawer__body--center">
              <span className="spin spin--lg" />
              <h3>Генерируем AI-отчёт…</h3>
              <p>Объясняем полученный результат на основе состава.</p>
            </div>
          )}

          {phase === "report" && (
            <div className="drawer__body">
              <div className="drawer__report-head"><p className="eyebrow">Отчёт по продукту</p>{score != null && <ScoreBadge score={score} />}</div>
              <p className="drawer__report-summary">{reportText || `Результат ${score}% — ${verdict?.toLowerCase()}. Состав в целом соответствует вашему профилю: увлажняющие и успокаивающие компоненты поддерживают барьер, агрессивных активов нет.`}</p>
              <section><h4>Почему такой результат</h4><ul className="obs">{safe.map((s) => <li key={s}><Icon name="check" size={15} /><span>{s}</span></li>)}</ul></section>
              <section><h4>Проблемные моменты</h4><ul className="obs obs--warn">{caution.map((s) => <li key={s}><Icon name="alert" size={15} /><span>{s}</span></li>)}</ul></section>
              <section><h4>Ключевые компоненты</h4><ul className="actives">{actives.map((a) => (<li key={a.name}><span className="actives__name">{a.name}</span><span className="actives__effect">{a.effect}</span><span className="actives__conc">{a.conc}</span></li>))}</ul></section>
              <section><h4>Состав (INCI)</h4><p className="inci">Aqua, Glycerin, Butylene Glycol, Sodium Hyaluronate, Niacinamide, Panthenol, Allantoin, Carbomer, Phenoxyethanol.</p></section>
              {similar.length > 0 && (<section><h4>Проверьте ещё</h4><div className="rec-list">{similar.map((p) => (<button key={p.id} type="button" className="rec" onClick={() => onOpen(p)}><img src={p.image} alt="" loading="lazy" /><span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>{p.score != null && <ScoreBadge score={p.score} />}</button>))}</div></section>)}
            </div>
          )}

          <div className="drawer__body drawer__review">
            <h4>Оценка и отзыв</h4>
            <div className="stars">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" className={`star ${rating >= n ? "star--on" : ""}`} onClick={() => setRating(n)} aria-label={`${n} звёзд`}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill={rating >= n ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z" /></svg>
                </button>
              ))}
            </div>
            <textarea className="review-input" value={review} onChange={(e) => setReview(e.target.value)} placeholder="Поделитесь впечатлением о продукте…" rows={3} />
            <label className="review-anon"><input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} /> Оставить анонимно</label>
            <Button small onClick={submitReview} disabled={rating === 0}>{sent ? "Спасибо за отзыв!" : "Отправить отзыв"}</Button>
          </div>
        </div>
        <div className="drawer__footer"><Button variant="ghost" onClick={close}>Закрыть</Button></div>
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

  const submit = async () => {
    setError("")
    if (!email.trim() || !pass) { setError("Введите email и пароль"); return }
    if (mode === "register" && !name.trim()) { setError("Введите имя"); return }
    setLoading(true)
    try {
      if (mode === "login") {
        const res = await api.login(email.trim(), pass)
        setToken(res.access_token)
        const displayName = res.user.name || email.trim().split("@")[0]
        onSuccess({ name: displayName, initials: displayName.slice(0, 2).toUpperCase(), plan: "plus", points: 40 })
      } else {
        await api.register(email.trim(), pass, name.trim())
        setSent(true)
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
          {error && <p className="auth-modal__error">{error}</p>}
          <Button className="w-full" onClick={submit} disabled={loading}>{loading ? "Подождите…" : mode === "login" ? "Войти" : "Зарегистрироваться"}</Button>
          <div className="auth-modal__divider">или</div>
          <a href="/api/auth/google" className="google-btn">
            <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"/><path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A11 11 0 0 0 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/></svg>
            Войти через Google
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
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--wide" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="pricing">
          <p className="eyebrow">Подписка</p>
          <h2>Тарифы</h2>
          <p className="pricing__hint">Сравните возможности тарифов и выберите подходящий. Текущий тариф выделен цветом.</p>
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

function ShelfAddModal({ items, onClose, onAdd, onScan }: { items: Product[]; onClose: () => void; onAdd: (id: number) => void; onScan: (m: ScanMethod) => void }) {
  const [mode, setMode] = useState<"menu" | "catalog" | "auto">("menu")
  const [q, setQ] = useState("")
  const list = items.filter((p) => {
    const n = q.trim().toLowerCase()
    if (mode === "auto") return p.score != null && p.score >= 80 && !p.state
    if (!n) return !p.state
    return [p.name, p.brand, p.category, ...p.tags].join(" ").toLowerCase().includes(n)
  }).slice(0, 8)
  const title = mode === "catalog" ? "Из каталога" : mode === "auto" ? "Автоподбор" : "Добавить средство"
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="add-modal">
          <p className="eyebrow">Моя полка</p>
          <h2>{title}</h2>
          {mode === "menu" && (
            <>
              <button type="button" className="add-menu__auto" onClick={() => setMode("auto")}>
                <span className="add-menu__auto-icon"><Icon name="sparkle" size={22} /></span>
                <span><strong>Автоподбор продукта</strong><small>Подберём средства под вашу кожу и полку</small></span>
                <Icon name="chevron" size={18} />
              </button>
              <div className="add-menu__grid">
                <button type="button" className="add-menu__opt" onClick={() => setMode("catalog")}><Icon name="box" size={18} /><span>Из каталога</span></button>
                <button type="button" className="add-menu__opt" onClick={() => onScan("photo")}><Icon name="camera" size={18} /><span>По фото упаковки</span></button>
                <button type="button" className="add-menu__opt" onClick={() => onScan("inci")}><Icon name="drop" size={18} /><span>По фото состава</span></button>
                <button type="button" className="add-menu__opt" onClick={() => onScan("manual")}><Icon name="pencil" size={18} /><span>Ручной ввод</span></button>
              </div>
            </>
          )}
          {(mode === "catalog" || mode === "auto") && (
            <>
              <button type="button" className="add-modal__back" onClick={() => setMode("menu")}><Icon name="back" size={15} /> Назад</button>
              {mode === "catalog" && <div className="search"><Icon name="search" size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Название, бренд или актив…" /></div>}
              <div className="add-modal__list">
                {list.map((p) => (
                  <button key={p.id} type="button" className="rec" onClick={() => onAdd(p.id)}>
                    <img src={p.image} alt="" loading="lazy" />
                    <span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>
                    <span className="add-modal__add"><Icon name="plus" size={16} /></span>
                  </button>
                ))}
                {list.length === 0 && <p className="empty">Ничего не нашлось.</p>}
              </div>
            </>
          )}
        </div>
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

export default function App() {
  const [items, setItems] = useState<Product[]>(products)
  const [shelfItems, setShelfItems] = useState<Product[]>([])
  const [page, setPage] = useState<Page>("home")
  const [open, setOpen] = useState<Product | null>(null)
  const [checkingIds, setCheckingIds] = useState<Set<number>>(new Set())
  const [user, setUser] = useState<User | null>(null)
  const [authModal, setAuthModal] = useState<null | "login" | "register">(null)
  const [pricingOpen, setPricingOpen] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [pointsOpen, setPointsOpen] = useState(false)
  const [scanMethod, setScanMethod] = useState<ScanMethod | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState("")
  const [helpOpen, setHelpOpen] = useState(false)
  const [toast, setToast] = useState("")

  useEffect(() => { const t = window.setTimeout(() => setLoading(false), 1200); return () => window.clearTimeout(t) }, [])
  useEffect(() => { if (!toast) return; const t = window.setTimeout(() => setToast(""), 2200); return () => window.clearTimeout(t) }, [toast])

  // Восстановление сессии по сохранённому токену (в т.ч. Google OAuth ?token=).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlToken = params.get("token")
    if (urlToken) {
      setToken(urlToken)
      params.delete("token")
      const qs = params.toString()
      window.history.replaceState(null, "", window.location.pathname + (qs ? "?" + qs : ""))
    }
    const token = getToken()
    if (!token) return
    api.me()
      .then((u) => {
        const displayName = u.name || u.email?.split("@")[0] || "Пользователь"
        setUser({ name: displayName, initials: displayName.slice(0, 2).toUpperCase(), plan: "plus", points: 40 })
      })
      .catch(() => setToken(null))
  }, [])

  // Загрузка реальных продуктов из каталога (фолбэк — mock).
  useEffect(() => {
    api.catalog({ limit: 200, sort: "popular" })
      .then((res) => {
        const mapped = (res.products || []).map(mapApiProduct).filter((p) => p.name && p.name !== "Продукт")
        if (mapped.length) setItems(mapped)
      })
      .catch(() => {})
  }, [])

  // Полка: грузим реальные шкафы и отмечаем продукты как «использую».
  const loadShelf = () => {
    if (!getToken()) return
    api.shelf()
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
        if (mapped.length) setShelfItems(mapped)
        if (shelfIds.size) setItems((cur) => cur.map((p) => (shelfIds.has(p.id) ? { ...p, state: "using" } : p)))
      })
      .catch(() => {})
  }
  useEffect(() => { loadShelf() }, [])

  // Блокируем прокрутку фона, когда открыт drawer или модалка.
  useEffect(() => {
    const locked = open != null || authModal != null || pricingOpen || addModalOpen || pointsOpen
    if (locked) {
      const prev = document.body.style.overflow
      document.body.style.overflow = "hidden"
      return () => { document.body.style.overflow = prev }
    }
  }, [open, authModal, pricingOpen, addModalOpen, pointsOpen])

  const navigate = (p: Page) => {
    if (p === "shelf" && !user) { setAuthModal("login"); return }
    if (p === "report") { setToast("Раздел «Отчёт» скоро появится"); return }
    if (p === "scan") setScanMethod(null)
    setPage(p)
    window.scrollTo({ top: 0 })
  }

  const onChecking = (id: number) => setCheckingIds((prev) => new Set(prev).add(id))
  const onChecked = (id: number, score: number, verdict: Verdict) => {
    setItems((cur) => cur.map((p) => (p.id === id ? { ...p, checked: true, score, verdict } : p)))
    setOpen((o) => (o && o.id === id ? { ...o, checked: true, score, verdict } : o))
    setCheckingIds((prev) => { const n = new Set(prev); n.delete(id); return n })
  }
  const onReported = (id: number) => {
    setItems((cur) => cur.map((p) => (p.id === id ? { ...p, report: true } : p)))
    setOpen((o) => (o && o.id === id ? { ...o, report: true } : o))
  }

  const handleLogin = (u: User) => { setUser(u); setAuthModal(null) }
  const handleLogout = () => { setToken(null); setUser(null); if (page === "shelf" || page === "report") setPage("home") }
  const handleSelectPlan = (p: Plan) => { setUser((u) => (u ? { ...u, plan: p, points: PLANS.find((x) => x.key === p)?.monthlyPoints ?? u.points } : u)) }
  const handleAddToShelf = async (id: number) => {
    const p = items.find((x) => x.id === id)
    if (p?.slug && getToken()) {
      try { await api.addToShelf(p.slug, p.category || "", p.cabinet || "face") } catch { /* ignore */ }
    }
    setItems((cur) => cur.map((x) => (x.id === id && !x.state ? { ...x, state: "want" } : x)))
    setAddModalOpen(false)
    loadShelf()
  }
  const handleTopUp = (amount: number) => {
    setUser((u) => (u ? { ...u, points: u.points + amount } : u))
  }
  const handleScanFromAdd = (m: ScanMethod) => {
    setAddModalOpen(false)
    setScanMethod(m)
    setPage("scan")
    window.scrollTo({ top: 0 })
  }
  const goToCatalog = (q: string) => { setQuery(q); setPage("catalog"); window.scrollTo({ top: 0 }) }

  return (
    <div className="app-shell">
      <LoadingScreen done={!loading} />
      <Sidebar page={page} onNavigate={navigate} user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onPoints={() => setPointsOpen(true)} />
      <div className="workspace">
        <Topbar page={page} onNavigate={navigate} onHelp={() => setHelpOpen(true)} user={user} onAuth={() => setAuthModal("login")} onPoints={() => setPointsOpen(true)} />
        <GlobalBar query={query} onQuery={setQuery} user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onPoints={() => setPointsOpen(true)} onLogout={handleLogout} onNavigate={navigate} onOpen={setOpen} onHelp={() => setHelpOpen(true)} />
        <main className="main-content">
          <div key={page} className="page-anim">
            {page === "home" && <HomePage onNavigate={navigate} onOpen={setOpen} onScan={() => navigate("scan")} user={user} />}
            {page === "shelf" && <ShelfPage items={shelfItems.length ? shelfItems : items} checkingIds={checkingIds} onOpen={setOpen} onAdd={() => setAddModalOpen(true)} />}
            {page === "scan" && <ScanPage onContinue={setOpen} initialMethod={scanMethod ?? undefined} />}
            {page === "catalog" && <CatalogPage items={items} checkingIds={checkingIds} onOpen={setOpen} query={query} onQuery={setQuery} />}
            {page === "profile" && <ProfilePage user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onLogout={handleLogout} onPoints={() => setPointsOpen(true)} />}
          </div>
        </main>
      </div>
      <BottomNav page={page} onNavigate={navigate} />
      {open && <ProductDrawer key={open.id} product={open} user={user} onAuth={() => setAuthModal("login")} onPricing={() => setPricingOpen(true)} onClose={() => setOpen(null)} onChecking={onChecking} onChecked={onChecked} onReported={onReported} onOpen={setOpen} onGoToCatalog={goToCatalog} />}
      {authModal && <AuthModal mode={authModal} onClose={() => setAuthModal(null)} onSuccess={handleLogin} onSwitch={setAuthModal} />}
      {pricingOpen && <PricingModal user={user} onClose={() => setPricingOpen(false)} onSelectPlan={handleSelectPlan} />}
      {pointsOpen && <PointsModal user={user} onClose={() => setPointsOpen(false)} onTopUp={handleTopUp} />}
      {addModalOpen && <ShelfAddModal items={items} onClose={() => setAddModalOpen(false)} onAdd={handleAddToShelf} onScan={handleScanFromAdd} />}
      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
