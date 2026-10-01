import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  products, skinProfile, shelfReport, CATEGORIES,
  SKIN_TYPE_OPTIONS, AGE_OPTIONS, CONCERN_CARDS, THERAPY_OPTIONS, RETINOID_OPTIONS,
  ACID_OPTIONS, PROCEDURE_OPTIONS, PROCEDURE_PERIODS, INTOLERANCE_OPTIONS, GOALS_OPTIONS,
  type Page, type Product, type ProductState, type Verdict, type QuizBranch, type QuizQuestion, type QuizOption,
} from "./data"

type IconName =
  | "home" | "shelf" | "scan" | "search" | "chart" | "user"
  | "arrow" | "chevron" | "close" | "check" | "plus" | "sparkle"
  | "drop" | "shield" | "file" | "bookmark" | "box" | "alert" | "camera" | "upload" | "back"

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
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  )
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

type Tone = "good" | "warn" | "bad" | "neutral"
function toneOf(score: number | null, verdict: Verdict | null): Tone {
  if (verdict === "Подходит") return "good"
  if (verdict === "Не подходит") return "bad"
  if (verdict === "С осторожностью") return "warn"
  if (score != null && score >= 80) return "good"
  if (score != null && score >= 60) return "warn"
  if (score != null) return "bad"
  return "neutral"
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
function Avatar({ size = 34 }: { size?: number }) {
  return <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.42 }}>{skinProfile.initials}</span>
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
          <h3 className="pcard__name">{product.name}</h3>
          <p className="pcard__cat">{product.category}</p>
        </div>
      </button>
      <div className="pcard__foot">
        {checked ? (
          <>
            <VerdictPill verdict={product.verdict} score={product.score} />
            <button type="button" className="pcard__link" onClick={onOpen}>{product.report ? "Отчёт" : "Подробнее"} <Icon name="chevron" size={13} /></button>
          </>
        ) : checking ? (
          <span className="pcard__checking"><span className="spin" /> Проверяем…</span>
        ) : (
          <button type="button" className="pcard__check" onClick={onOpen}>
            <Icon name="sparkle" size={13} /> Проверить совместимость
          </button>
        )}
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

function Sidebar({ page, onNavigate }: { page: Page; onNavigate: (p: Page) => void }) {
  return (
    <aside className="sidebar">
      <div className="brand"><span className="brand__mark">A</span><strong>Aidermy</strong></div>
      <nav className="nav-list">
        {NAV.map((item) => (
          <button key={item.id} type="button" className={`nav-item ${page === item.id ? "nav-item--active" : ""}`} onClick={() => onNavigate(item.id)}>
            <Icon name={item.icon} /> {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-card">
        <span className="sidebar-card__icon"><Icon name="sparkle" /></span>
        <strong>Интеллектуальная проверка</strong>
        <p>Состав → связи → совместимость с вашей кожей.</p>
      </div>
      <button type="button" className="profile-mini" onClick={() => onNavigate("profile")}>
        <Avatar size={30} />
        <span><strong>{skinProfile.name}</strong><small>{skinProfile.skinType}</small></span>
        <Icon name="chevron" size={15} />
      </button>
    </aside>
  )
}
function Topbar({ page, onNavigate, onScan }: { page: Page; onNavigate: (p: Page) => void; onScan: () => void }) {
  const title = NAV.find((n) => n.id === page)?.label ?? ""
  return (
    <header className="topbar">
      <span className="topbar__brand"><span className="brand__mark brand__mark--sm">A</span><strong>Aidermy</strong></span>
      <span className="topbar__title">{title}</span>
      <div className="topbar__actions">
        <button type="button" className="icon-btn" onClick={onScan} aria-label="Сканировать"><Icon name="scan" size={19} /></button>
        <button type="button" className="icon-btn" onClick={() => onNavigate("profile")} aria-label="Профиль"><Avatar size={28} /></button>
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

function HomePage({ onNavigate, onOpen, onScan }: { onNavigate: (p: Page) => void; onOpen: (p: Product) => void; onScan: () => void }) {
  const using = products.filter((p) => p.state === "using").slice(0, 4)
  const recent = products.filter((p) => p.checked).slice(0, 6)
  const trend = shelfReport.compatibilityHistory.map((h) => h.shelfAverage)
  return (
    <div className="page">
      <section className="hero">
        <ParticleCanvas />
        <div className="hero__inner">
          <p className="eyebrow">Доброе утро, {skinProfile.name}</p>
          <h1 className="hero__title">Косметика, которая<br />действительно подходит</h1>
          <p className="hero__lead">Aidermy связывает состав с вашей кожей и показывает, что сработает, а что нет.</p>
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
            <div className="report-preview__side">
              <p className="report-preview__label">средняя совместимость полки</p>
              <Sparkline values={trend} />
              <p className="report-preview__hint">по {shelfReport.compatibilityHistory.length} проверенным продуктам</p>
            </div>
          </div>
        </section>

        <section className="panel">
          <p className="eyebrow">Профиль кожи</p>
          <h3 className="panel__h3">{skinProfile.skinType}</h3>
          <div className="chips">
            {skinProfile.goals.map((g) => <span key={g} className="chip">{g}</span>)}
            <span className="chip chip--warn">чувствительная</span>
          </div>
          <Button variant="ghost" small icon="user" onClick={() => onNavigate("profile")} className="mt">Изменить опрос</Button>
        </section>
      </div>

      <section className="block">
        <SectionHead eyebrow="Недавно" title="Проверенные продукты" action={() => onNavigate("catalog")} actionLabel="Все" />
        <div className="hscroll">
          {recent.map((p) => <ProductCard key={p.id} product={p} onOpen={() => onOpen(p)} />)}
        </div>
      </section>

      <section className="block">
        <SectionHead eyebrow="Моя полка" title="Сейчас использую" action={() => onNavigate("shelf")} actionLabel="Полка" />
        <div className="hscroll">
          {using.map((p) => <ProductCard key={p.id} product={p} onOpen={() => onOpen(p)} />)}
        </div>
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
  const [filter, setFilter] = useState<"all" | ProductState>("all")
  const states: { id: "all" | ProductState; label: string }[] = [
    { id: "all", label: "Все" },
    { id: "using", label: "Сейчас использую" },
    { id: "want", label: "Хочу попробовать" },
    { id: "finished", label: "Закончились" },
  ]
  const shelved = items.filter((p) => p.state)
  const filtered = filter === "all" ? shelved : shelved.filter((p) => p.state === filter)
  const usingCount = items.filter((p) => p.state === "using").length
  const scored = items.filter((p) => p.state && p.score != null)
  const avg = scored.length ? Math.round(scored.reduce((s, p) => s + (p.score ?? 0), 0) / scored.length) : null
  return (
    <div className="page">
      <PageHeading eyebrow="Уход" title="Моя полка" lead="Полка растёт вместе с уходом: категории и статусы — отдельные измерения."
        action={<Button icon="plus" onClick={onAdd}>Добавить средство</Button>} />
      <div className="shelf-summary">
        <div><strong>{usingCount}</strong><span>сейчас использую</span></div>
        <div><strong>{avg != null ? `${avg}%` : "—"}</strong><span>средняя совместимость</span></div>
        <div><strong>{shelfReport.attention.length}</strong><span>на что обратить внимание</span></div>
      </div>
      <div className="tabs">
        {states.map((s) => (
          <button key={s.id} type="button" className={`tab ${filter === s.id ? "tab--active" : ""}`} onClick={() => setFilter(s.id)}>{s.label}</button>
        ))}
      </div>
      {CATEGORIES.map((cat) => {
        const list = filtered.filter((p) => p.category === cat)
        if (!list.length) return null
        const catAvg = list.filter((p) => p.score != null).length ? Math.round(list.filter((p) => p.score != null).reduce((s, p) => s + (p.score ?? 0), 0) / list.filter((p) => p.score != null).length) : null
        return (
          <section key={cat} className="shelf-board">
            <div className="shelf-board__head">
              <h3>{cat}</h3>
              <span>{list.length} средств{catAvg != null ? ` · ${catAvg}%` : ""}</span>
            </div>
            <div className="shelf-board__rack">
              {list.map((p) => (
                <ProductCard key={p.id} product={p} checking={checkingIds.has(p.id)} onOpen={() => onOpen(p)} />
              ))}
              <button type="button" className="shelf-add" onClick={onAdd} aria-label="Добавить продукт">
                <Icon name="plus" size={26} />
              </button>
            </div>
            <div className="shelf-plank"><span /><span /></div>
          </section>
        )
      })}
    </div>
  )
}

function CatalogPage({ items, checkingIds, onOpen }: {
  items: Product[]; checkingIds: Set<number>; onOpen: (p: Product) => void
}) {
  const [query, setQuery] = useState("")
  const [cat, setCat] = useState<string>("Все")
  const list = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return items.filter((p) => {
      if (cat !== "Все" && p.category !== cat) return false
      if (!needle) return true
      return [p.name, p.brand, p.category, ...p.tags].join(" ").toLowerCase().includes(needle)
    })
  }, [items, query, cat])
  return (
    <div className="page">
      <PageHeading eyebrow="База продуктов" title="Каталог" lead="Проверяйте составы и находите продукты под особенности вашей кожи." />
      <div className="search">
        <Icon name="search" size={18} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название, бренд или актив…" />
        {query && <button type="button" onClick={() => setQuery("")} className="search__clear" aria-label="Очистить"><Icon name="close" size={15} /></button>}
      </div>
      <div className="tabs">
        {["Все", ...CATEGORIES].map((c) => (
          <button key={c} type="button" className={`tab ${cat === c ? "tab--active" : ""}`} onClick={() => setCat(c)}>{c}</button>
        ))}
      </div>
      <div className="product-grid">
        {list.map((p) => (
          <ProductCard key={p.id} product={p} checking={checkingIds.has(p.id)} onOpen={() => onOpen(p)} />
        ))}
      </div>
      {list.length === 0 && <p className="empty">Ничего не нашлось. Попробуйте другой запрос.</p>}
    </div>
  )
}
function ScanPage({ onContinue }: { onContinue: (p: Product) => void }) {
  const [phase, setPhase] = useState<"input" | "recognizing" | "ready">("input")
  const [inci, setInci] = useState("")
  const sample = products[6]
  const run = () => { setPhase("recognizing"); window.setTimeout(() => setPhase("ready"), 1500) }
  return (
    <div className="page">
      <PageHeading eyebrow="Проверка" title="Сканировать продукт" lead="Сфотографируйте упаковку — определим продукт и продолжим анализ." />
      {phase === "input" && (
        <div className="scan">
          <div className="scan__main">
            <div className="scan__drop">
              <span className="scan__drop-icon"><Icon name="camera" size={30} /></span>
              <h3>Сфотографируйте упаковку</h3>
              <p>Наведите камеру на этикетку — распознаем продукт и состав.</p>
              <div className="scan__drop-actions">
                <Button icon="camera" onClick={run}>Сделать фото</Button>
                <Button variant="secondary" icon="upload" onClick={run}>Загрузить изображение</Button>
              </div>
            </div>
          </div>
          <div className="scan__alt">
            <p className="eyebrow">Другой способ</p>
            <h3>Вставить состав вручную</h3>
            <p className="scan__alt-hint">Если фото недоступно — вставьте INCI-список.</p>
            <textarea value={inci} onChange={(e) => setInci(e.target.value)} placeholder="Aqua, Glycerin, Niacinamide…" rows={4} />
            <Button icon="sparkle" onClick={run} className="w-full">Проверить состав</Button>
          </div>
        </div>
      )}
      {phase === "recognizing" && (
        <div className="scan-status">
          <span className="spin spin--lg" />
          <h3>Распознаём продукт…</h3>
          <p>Определяем бренд и название по фото упаковки.</p>
        </div>
      )}
      {phase === "ready" && (
        <div className="scan-ready panel">
          <p className="eyebrow">Продукт определён</p>
          <div className="scan-ready__row">
            <img src={sample.image} alt="" />
            <div>
              <h3>{sample.name}</h3>
              <p>{sample.brand} · {sample.category}</p>
              <VerdictPill verdict={sample.verdict} score={sample.score} />
            </div>
          </div>
          <div className="scan-ready__actions">
            <Button icon="sparkle" onClick={() => onContinue(sample)}>Продолжить анализ</Button>
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
    <svg viewBox={`0 0 ${w} ${h}`} className="compat-chart" role="img" aria-label="Средняя совместимость полки по мере проверки продуктов">
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
  const history = shelfReport.compatibilityHistory
  const want = products.filter((p) => p.state === "want").slice(0, 3)
  return (
    <div className="page">
      <PageHeading eyebrow="Сводка" title="Отчёт" lead="Быстрое понимание состояния вашей косметики." />
      <section className="report-hero">
        <div className="report-hero__num"><strong>{shelfReport.average}</strong><span>%</span></div>
        <div className="report-hero__side">
          <p>Средняя совместимость полки</p>
          <CompatChart history={history} />
        </div>
      </section>
      <p className="report-metric-note">Средняя совместимость средств на полке — по мере проверки продуктов (кумулятивно).</p>
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







function ProfilePage() {
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
  return (
    <div className="page">
      <PageHeading eyebrow="Профиль" title="Профиль кожи" lead="На основе профиля рассчитывается совместимость каждого продукта."
        action={<Button icon="user" onClick={() => setQuiz(true)}>Изменить опрос</Button>} />
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

function ProductDrawer({ product, onClose, onChecking, onChecked, onReported, onOpen }: {
  product: Product; onClose: () => void; onChecking: (id: number) => void; onChecked: (id: number, score: number, verdict: Verdict) => void; onReported: (id: number) => void; onOpen: (p: Product) => void
}) {
  const [phase, setPhase] = useState<"idle" | "checking" | "match" | "generating" | "report">(
    product.checked && product.report ? "report" : product.checked ? "match" : "idle"
  )
  const [score, setScore] = useState<number | null>(product.score)
  const [verdict, setVerdict] = useState<Verdict | null>(product.verdict)

  const check = () => {
    setPhase("checking")
    onChecking(product.id)
    window.setTimeout(() => {
      const s = 60 + ((product.id * 13) % 35)
      const v: Verdict = s >= 80 ? "Подходит" : s >= 60 ? "С осторожностью" : "Не подходит"
      setScore(s); setVerdict(v); setPhase("match")
      onChecked(product.id, s, v)
    }, 1300)
  }
  const showReport = () => { setPhase("generating"); window.setTimeout(() => { setPhase("report"); onReported(product.id) }, 1600) }

  const safe = product.tags.length ? product.tags.map((t) => `${t} — совместимо с профилем`) : ["Базовый состав без явных конфликтов"]
  const caution = verdict === "Не подходит" ? ["Содержит активы, агрессивные для чувствительной кожи", "Конфликт с текущим ретиноидом"] : verdict === "С осторожностью" ? ["Возможна реакция при сочетании с ретиноидом", "Начинайте с низкой частоты"] : ["Явных противопоказаний не найдено"]
  const actives = [
    { name: "Гиалуроновая кислота", conc: "средняя", effect: "удерживает влагу" },
    { name: "Ниацинамид", conc: "низкая", effect: "выравнивает тон" },
    { name: "Пантенол", conc: "средняя", effect: "успокаивает" },
  ]
  const similar = products.filter((p) => p.category === product.category && p.id !== product.id).slice(0, 3)

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <button type="button" className="drawer__close" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={18} /></button>
        <div className="drawer__scroll">
          <div className="drawer__hero">
            <img src={product.image} alt="" />
            <div className="drawer__hero-meta">
              <p className="eyebrow">{product.brand}</p>
              <h2>{product.name}</h2>
              <p className="drawer__cat">{product.category}</p>
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
              <div className="drawer__cta"><Button icon="file" className="w-full" onClick={showReport}>Показать отчёт</Button></div>
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
              <p className="drawer__report-summary">Результат {score}% — {verdict?.toLowerCase()}. Состав в целом соответствует вашему профилю: увлажняющие и успокаивающие компоненты поддерживают барьер, агрессивных активов нет.</p>
              <section><h4>Почему такой результат</h4><ul className="obs">{safe.map((s) => <li key={s}><Icon name="check" size={15} /><span>{s}</span></li>)}</ul></section>
              <section><h4>Проблемные моменты</h4><ul className="obs obs--warn">{caution.map((s) => <li key={s}><Icon name="alert" size={15} /><span>{s}</span></li>)}</ul></section>
              <section><h4>Ключевые компоненты</h4><ul className="actives">{actives.map((a) => (<li key={a.name}><span className="actives__name">{a.name}</span><span className="actives__effect">{a.effect}</span><span className="actives__conc">{a.conc}</span></li>))}</ul></section>
              <section><h4>Состав (INCI)</h4><p className="inci">Aqua, Glycerin, Butylene Glycol, Sodium Hyaluronate, Niacinamide, Panthenol, Allantoin, Carbomer, Phenoxyethanol.</p></section>
              {similar.length > 0 && (<section><h4>Проверьте ещё</h4><div className="rec-list">{similar.map((p) => (<button key={p.id} type="button" className="rec" onClick={() => onOpen(p)}><img src={p.image} alt="" loading="lazy" /><span><strong>{p.name}</strong><small>{p.brand} · {p.category}</small></span>{p.score != null && <ScoreBadge score={p.score} />}</button>))}</div></section>)}
            </div>
          )}

        </div>
        <div className="drawer__footer"><Button variant="ghost" onClick={onClose}>Закрыть</Button></div>
      </aside>
    </>
  )
}
export default function App() {
  const [items, setItems] = useState<Product[]>(products)
  const [page, setPage] = useState<Page>("home")
  const [open, setOpen] = useState<Product | null>(null)
  const [checkingIds, setCheckingIds] = useState<Set<number>>(new Set())

  const navigate = (p: Page) => { setPage(p); window.scrollTo({ top: 0 }) }

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

  return (
    <div className="app-shell">
      <Sidebar page={page} onNavigate={navigate} />
      <div className="workspace">
        <Topbar page={page} onNavigate={navigate} onScan={() => navigate("scan")} />
        <main className="main-content">
          {page === "home" && <HomePage onNavigate={navigate} onOpen={setOpen} onScan={() => navigate("scan")} />}
          {page === "shelf" && <ShelfPage items={items} checkingIds={checkingIds} onOpen={setOpen} onAdd={() => navigate("catalog")} />}
          {page === "scan" && <ScanPage onContinue={setOpen} />}
          {page === "catalog" && <CatalogPage items={items} checkingIds={checkingIds} onOpen={setOpen} />}
          {page === "report" && <ReportPage onOpen={setOpen} />}
          {page === "profile" && <ProfilePage />}
        </main>
      </div>
      <BottomNav page={page} onNavigate={navigate} />
      {open && <ProductDrawer key={open.id} product={open} onClose={() => setOpen(null)} onChecking={onChecking} onChecked={onChecked} onReported={onReported} onOpen={setOpen} />}
    </div>
  )
}



