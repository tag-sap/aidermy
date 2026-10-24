// evaluation-v2.tsx - пользовательский результат Evaluation V2.
// Общий вердикт + основная функция + персональные пункты со значками.
// Технические статусы и средние баллы остаются в backend/snapshot; неизвестные
// пункты показываются нейтральным прочерком, а не положительной галочкой.
import { useEffect, useId, useMemo, useState } from "react"
import {
  api,
  ApiError,
  EVALUATION_V2_ENABLED,
  type EvaluationComedogenicity,
  type EvaluationOverall,
  type EvaluationPersonalParameter,
  type EvaluationPrimaryFunction,
  type EvaluationReport,
} from "./api"

const VALUE_LABEL: Record<string, string> = {
  "skin_type:dry": "Тип кожи: сухая",
  "skin_type:oily": "Тип кожи: жирная",
  "skin_type:normal": "Тип кожи: нормальная",
  "skin_type:combination": "Тип кожи: комбинированная",
  "problem:dryness": "Задача: сухость и обезвоженность",
  "problem:acne_general": "Задача: склонность к акне",
  "problem:acne": "Задача: склонность к акне",
  "goal:hydration": "Цель: увлажнение",
  "goal:acne": "Цель: уменьшить акне",
  "intolerance:niacinamide_intolerance": "Наличие в составе: ниацинамид",
  "intolerance:fragrance_intolerance": "Наличие в составе: отдушки",
  "intolerance:alcohol_intolerance": "Наличие в составе: спирт",
  "intolerance:acid_intolerance": "Наличие в составе: кислоты",
  "intolerance:retinoid_intolerance": "Наличие в составе: ретиноиды",
  "therapy:adapalene": "Совместимость с лечением адапаленом",
  "therapy:antibiotic": "Совместимость с антибактериальной терапией",
  "therapy:benzoyl_peroxide": "Совместимость с бензоилпероксидом",
  "therapy:tretinoin": "Совместимость с третиноином",
  "therapy:acid_therapy": "Совместимость с кислотной терапией",
  "procedure:recent_biorevitalization@<7": "Уход после биоревитализации: первые 7 дней",
  "procedure:recent_laser@<7": "Уход после лазерной процедуры: первые 7 дней",
  "procedure:recent_peeling@<7": "Уход после пилинга: первые 7 дней",
}

function parameterLabel(parameterId: string): string {
  // The backend snapshot now carries a normal Russian label. Never fall back to
  // a machine id when an older snapshot is opened.
  return VALUE_LABEL[parameterId] || "Параметр профиля"
}

function cleanProductName(name: string): string {
  return (name || "").replace(/\s+/g, " ").trim()
}

function LoadingState({ label }: { label: string }) {
  const [dots, setDots] = useState(1)
  useEffect(() => {
    const timer = window.setInterval(() => setDots((value) => (value % 3) + 1), 380)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="evalv2__loading" role="status" aria-live="polite">
      <img src="/loading.gif" alt="" />
      <span>{label}{".".repeat(dots)}</span>
    </div>
  )
}

const VERDICT_ICON_BY_STATUS: Record<string, string> = {
  positive: "happy",
  negative: "dead",
  caution: "alert",
  neutral: "neutral",
  unknown: "neutral",
  // Older saved reports use glyph names; normalize them to the same artwork.
  check: "happy",
  cross: "dead",
  dash: "neutral",
}

type VerdictName = "dead" | "happy" | "neutral" | "alert"

const VERDICT_TUBE_PATH = "M30,30 L110,30 C115,30 120,35 118,45 L108,160 C107,168 100,175 90,175 L50,175 C40,175 33,168 32,160 L22,45 C20,35 25,30 30,30 Z"
const VERDICT_CAP_PATH = "M45,175 L95,175 L90,205 C90,208 86,210 80,210 L60,210 C54,210 50,208 50,205 Z"
const VERDICT_CRIMPS = [35, 45, 55, 65, 75, 85, 95, 105]

// The original sprite kept these colours only in a <style> block at the root
// of the external file. An external <use> is not required to import that
// stylesheet into the shadow tree, leaving paths at the SVG default fill
// (black). Keep the palette as data and paint every shape explicitly.
const VERDICT_PALETTE: Record<VerdictName, {
  body: [string, string]
  cap: [string, string]
  band: string
}> = {
  dead: { body: ["#EF4444", "#DC2626"], cap: ["#991B1B", "#7F1D1D"], band: "#B91C1C" },
  happy: { body: ["#10B981", "#059669"], cap: ["#065F46", "#047857"], band: "#047857" },
  neutral: { body: ["#3B82F6", "#2563EB"], cap: ["#1E40AF", "#1E3A8A"], band: "#1D4ED8" },
  alert: { body: ["#F59E0B", "#D97706"], cap: ["#92400E", "#78350F"], band: "#B45309" },
}

const VERDICT_FACE_LINE = {
  fill: "none",
  stroke: "#FFFFFF",
  strokeWidth: 3.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
}
const VERDICT_FACE_SOLID = { fill: "#FFFFFF", stroke: "none" }
const VERDICT_CRIMP = {
  stroke: "rgba(0, 0, 0, 0.2)",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
}

function iconName(verdict?: string, icon?: string): VerdictName {
  const value = icon || VERDICT_ICON_BY_STATUS[verdict || ""] || "neutral"
  return value === "dead" || value === "happy" || value === "neutral" || value === "alert"
    ? value
    : "neutral"
}

function VerdictFace({ name }: { name: VerdictName }) {
  if (name === "dead") {
    return (
      <g transform="translate(0, 10)">
        <line x1="52" y1="82" x2="64" y2="94" {...VERDICT_FACE_LINE} />
        <line x1="64" y1="82" x2="52" y2="94" {...VERDICT_FACE_LINE} />
        <line x1="76" y1="82" x2="88" y2="94" {...VERDICT_FACE_LINE} />
        <line x1="88" y1="82" x2="76" y2="94" {...VERDICT_FACE_LINE} />
        <path d="M55,120 Q62,115 70,120 T85,120" {...VERDICT_FACE_LINE} />
      </g>
    )
  }
  if (name === "alert") {
    return (
      <g transform="translate(0, 10)">
        <line x1="50" y1="74" x2="62" y2="78" {...VERDICT_FACE_LINE} strokeWidth={2.5} />
        <line x1="90" y1="78" x2="78" y2="74" {...VERDICT_FACE_LINE} strokeWidth={2.5} />
        <ellipse cx="56" cy="86" rx="5" ry="4" {...VERDICT_FACE_SOLID} />
        <ellipse cx="84" cy="86" rx="5" ry="4" {...VERDICT_FACE_SOLID} />
        <path d="M54,118 Q62,112 70,116 T86,112" {...VERDICT_FACE_LINE} />
      </g>
    )
  }
  if (name === "neutral") {
    return (
      <g transform="translate(0, 10)">
        <circle cx="56" cy="88" r="5" {...VERDICT_FACE_SOLID} />
        <circle cx="84" cy="88" r="5" {...VERDICT_FACE_SOLID} />
        <line x1="54" y1="115" x2="86" y2="115" {...VERDICT_FACE_LINE} />
      </g>
    )
  }
  return (
    <g transform="translate(0, 10)">
      <circle cx="56" cy="86" r="5" {...VERDICT_FACE_SOLID} />
      <circle cx="84" cy="86" r="5" {...VERDICT_FACE_SOLID} />
      <path d="M52,108 Q70,130 88,108" {...VERDICT_FACE_LINE} />
    </g>
  )
}

function VerdictIcon({
  verdict,
  icon,
  className = "",
}: {
  verdict?: string
  icon?: string
  className?: string
}) {
  const name = iconName(verdict, icon)
  const palette = VERDICT_PALETTE[name]
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "")
  const bodyGradient = `verdict-${uid}-body`
  const capGradient = `verdict-${uid}-cap`
  const shadow = `verdict-${uid}-shadow`
  return (
    <span
      className={`evalv2__verdict-icon evalv2__verdict-icon--${name} ${className}`.trim()}
      data-verdict-icon={name}
      aria-hidden="true"
    >
      <svg viewBox="5 5 130 215" focusable="false">
        <defs>
          <linearGradient id={bodyGradient} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={palette.body[0]} />
            <stop offset="100%" stopColor={palette.body[1]} />
          </linearGradient>
          <linearGradient id={capGradient} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={palette.cap[0]} />
            <stop offset="100%" stopColor={palette.cap[1]} />
          </linearGradient>
          <filter id={shadow} x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="8" stdDeviation="6" floodColor="#0F172A" floodOpacity="0.15" />
          </filter>
        </defs>
        <path
          d={VERDICT_TUBE_PATH}
          fill={`url(#${bodyGradient})`}
          filter={`url(#${shadow})`}
        />
        <rect x="25" y="20" width="90" height="10" rx="3" fill={palette.band} />
        {VERDICT_CRIMPS.map((x) => (
          <line key={x} x1={x} y1="23" x2={x} y2="27" {...VERDICT_CRIMP} />
        ))}
        <path d={VERDICT_CAP_PATH} fill={`url(#${capGradient})`} />
        <VerdictFace name={name} />
      </svg>
    </span>
  )
}

function itemVerdict(item: EvaluationPersonalParameter): string {
  if (item.verdict) return item.verdict
  if (item.intolerance) {
    return item.intolerance.state === "present" ? "negative"
      : item.intolerance.state === "absent" ? "positive" : "unknown"
  }
  // Older payloads may not carry a verdict. Never reconstruct a safety
  // warning from a low benefit score: only the backend may authorize caution.
  return item.score != null && item.score >= 75 ? "positive"
    : item.score != null ? "neutral" : "unknown"
}

function itemText(item: EvaluationPersonalParameter): string {
  if (item.display_text) return item.display_text
  const label = item.label || parameterLabel(item.parameter_id)
  const verdict = itemVerdict(item)
  if (verdict === "unknown") return `Не удалось определить: ${label}.`
  return `${label}: ${item.verdict_label || (verdict === "positive" ? "подходит" : verdict === "negative" ? "не подходит" : verdict === "caution" ? "возможна осторожность" : "нейтрально")}.`
}

function ReportHeader({ productName, overall }: { productName: string; overall: EvaluationOverall }) {
  return (
    <header className="evalv2__report-head">
      {productName && <h4 className="evalv2__product-name">{productName}</h4>}
      <div className="evalv2__overall-main">
        <strong className={`evalv2__overall-verdict evalv2__overall-verdict--${overall.tone}`}>
          {overall.verdict}
        </strong>
      </div>
      <p className="evalv2__overall-summary">{overall.summary}</p>
    </header>
  )
}

function FunctionLine({
  item,
  open,
  onToggle,
}: {
  item: EvaluationPrimaryFunction
  open: boolean
  onToggle: () => void
}) {
  const hasInfo = Boolean(item.reason || item.score_note || (item.basis && item.basis.length))
  return (
    <div className={`evalv2__function-line ${open ? "evalv2__function-line--open" : ""}`}>
      <p>
        <span>Основная функция:</span> <strong>{item.label}</strong>
        {item.purpose ? <span className="evalv2__function-purpose"> · {item.purpose}</span> : null}
      </p>
      {item.score != null && (
        <span className="evalv2__function-score-wrap">
          <span
            className="evalv2__function-score"
            aria-label={`Соответствие состава функции ${item.score} из 100`}
            title={item.score_note || "Оценка соответствия состава, не клиническая эффективность"}
          >
            {item.score}<small>%</small>
          </span>
          <span className="evalv2__function-score-caption">
            {item.score_label || "соответствие состава"}
          </span>
        </span>
      )}
      {hasInfo && (
        <button
          type="button"
          className="evalv2__info"
          aria-label="Объяснить основную функцию"
          aria-expanded={open}
          onClick={onToggle}
        >
          ⓘ
        </button>
      )}
      {open && (
        <div className="evalv2__info-text">
          {item.reason && <p>{item.reason}</p>}
          {item.score_note && <p className="evalv2__function-note">{item.score_note}</p>}
          {(item.basis || []).map((row, index) => (
            <p key={index}>
              <strong>{row.label}: </strong>
              {row.value}
            </p>
          ))}
          {item.score == null && item.label !== "Основная функция не определена" && (
            <p className="evalv2__function-note">
              Функция определена по категории; эффективность состава оценивается отдельно.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ComedogenicityLine({
  item,
  open,
  onToggle,
}: {
  item: EvaluationComedogenicity
  open: boolean
  onToggle: () => void
}) {
  // The block owns confirmed ingredient ratings in 1..5. It is never rendered
  // as "Недостаточно данных", and no product-level diagnosis is inferred.
  const flagged = item.ingredients || []
  if (item.status !== "assessed" || item.applicable === false || flagged.length === 0) return null
  const label = item.risk_label
    || (item.level === "high" ? "Высокий потенциальный риск"
      : item.level === "medium" ? "Средний потенциальный риск"
        : "Низкий потенциальный риск")
  const details = [item.reason, item.risk, item.recommendation].filter(
    (value): value is string => Boolean(value && value.trim())
  )
  return (
    <div className={`evalv2__function-line evalv2__comedo-line evalv2__comedo-line--${item.level || "unknown"}`}>
      <p>
        <span>Комедогенность:</span> <strong>{label}</strong>
        <span className="evalv2__function-purpose"> · по отдельным подтверждённым компонентам</span>
      </p>
      <ul className="evalv2__comedo-components" aria-label="Подтверждённые рейтинги комедогенности">
        {flagged.map((ingredient) => (
          <li key={`${ingredient.name}-${ingredient.rating}`}>
            <span>{ingredient.name}</span>
            <b>{ingredient.rating_label || `${ingredient.rating}/5`}</b>
          </li>
        ))}
      </ul>
      {details.length > 0 && (
        <button
          type="button"
          className="evalv2__info"
          aria-label="Объяснить оценку комедогенности"
          aria-expanded={open}
          onClick={onToggle}
        >
          ⓘ
        </button>
      )}
      {open && details.length > 0 && (
        <div className="evalv2__info-text">
          {details.map((text, index) => <p key={index}>{text}</p>)}
          {(item.basis || []).map((row, index) => (
            <p key={`basis-${index}`}><strong>{row.label}: </strong>{row.value}</p>
          ))}
        </div>
      )}
    </div>
  )
}

function VerdictRow({
  item,
  number,
  open,
  onToggle,
}: {
  item: EvaluationPersonalParameter
  number: number
  open: boolean
  onToggle: () => void
}) {
  const verdict = itemVerdict(item)
  const details = [
    { label: verdict === "caution" ? "Причина" : "", text: item.cause || item.explanation || item.reason },
    { label: "Возможный риск", text: item.risk || "" },
    { label: "Рекомендация", text: item.recommendation || "" },
    { label: "Роль продукта", text: item.scope_note || "" },
    { label: "", text: item.intolerance?.reason || "" },
  ].filter((detail) => Boolean(detail.text && detail.text.trim()))
  return (
    <li className={`evalv2__verdict-row evalv2__verdict-row--${verdict}`}>
      <span className="evalv2__num" aria-hidden="true">{number}.</span>
      <span className="evalv2__verdict-text">{itemText(item)}</span>
      <span className="evalv2__status" aria-label={item.verdict_label || verdict}>
        <VerdictIcon verdict={verdict} icon={item.verdict_icon} />
      </span>
      <button
        type="button"
        className="evalv2__info"
        aria-label={`Объяснить пункт: ${item.label || itemText(item)}`}
        aria-expanded={open}
        onClick={onToggle}
      >
        ⓘ
      </button>
      {open && details.length > 0 && (
        <div className="evalv2__info-text">
          {details.map((detail, index) => (
            <p key={index}>
              {detail.label ? <strong>{detail.label}: </strong> : null}
              {detail.text}
            </p>
          ))}
        </div>
      )}
    </li>
  )
}

export function EvaluationV2Panel({
  productId,
  profile,
  enabled = true,
  canRestore = true,
  onStarted,
}: {
  productId: number
  profile: Record<string, unknown>
  enabled?: boolean
  canRestore?: boolean
  onStarted?: () => void
}) {
  const [started, setStarted] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const [report, setReport] = useState<EvaluationReport | null>(null)
  const [notice, setNotice] = useState("")
  const [restoreReason, setRestoreReason] = useState("")
  const [restoreError, setRestoreError] = useState("")
  const [restoreAttempt, setRestoreAttempt] = useState(0)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set())
  const [functionInfoOpen, setFunctionInfoOpen] = useState(false)
  const [comedoOpen, setComedoOpen] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const profileKey = useMemo(() => JSON.stringify(profile || {}), [profile])

  useEffect(() => {
    if (!EVALUATION_V2_ENABLED || !enabled || !canRestore) {
      setRestoring(false)
      return
    }
    let cancelled = false
    setStarted(false)
    setRestoring(true)
    setReport(null)
    setError("")
    setNotice("")
    setRestoreReason("")
    setRestoreError("")
    setExpandedItems(new Set())
    setFunctionInfoOpen(false)
    setComedoOpen(false)
    setSourcesOpen(false)

    api.evaluationProductSavedReport(productId, JSON.parse(profileKey))
      .then((result) => {
        if (cancelled) return
        if (!result.saved || !result.report) {
          setRestoreReason(
            result.reason || "Сохранённого отчёта для текущего профиля нет или он устарел."
          )
          return
        }
        setReport(result.report)
        setStarted(true)
        onStarted?.()
      })
      .catch(() => {
        if (!cancelled) {
          // An API/network error is not the same as an absent report: keep the
          // error visible and never start a new analysis automatically.
          setRestoreError("Не удалось загрузить сохранённый отчёт. Проверьте соединение и попробуйте снова.")
        }
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => { cancelled = true }
  }, [productId, profileKey, enabled, canRestore, restoreAttempt])

  const start = async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setStarted(true)
    onStarted?.()
    setLoading(true)
    setError("")
    setNotice("")
    setRestoreReason("")
    setRestoreError("")
    setReport(null)
    try {
      const checked = await api.evaluationCompositionCheck(productId)
      if (!checked.composition_state?.usable) {
        setNotice(checked.message || "Не удалось подтвердить состав продукта.")
        return
      }
      const data = await api.evaluationProductEvaluate(
        productId,
        JSON.parse(profileKey)
      )
      setReport(data)
    } catch (e) {
      const statusCode = e instanceof ApiError ? e.status : 0
      if (statusCode === 401) {
        setError("Войдите, чтобы проверить продукт.")
      } else if (statusCode === 503) {
        setError("Проверка временно недоступна.")
      } else if (statusCode === 409) {
        setError(e instanceof ApiError ? e.message : "Проверка не запущена: недостаточно баллов.")
      } else {
        setError("Не удалось проверить продукт. Попробуйте позже.")
      }
    } finally {
      setLoading(false)
    }
  }

  const userReport = report?.user_report
  const primary = userReport?.primary_function ?? report?.primary_function ?? null
  const topLevelComedo = report?.comedogenicity && Object.keys(report.comedogenicity).length
    ? report.comedogenicity
    : null
  const rawComedogenicity = userReport?.comedogenicity ?? topLevelComedo
  const comedogenicity = rawComedogenicity?.status === "assessed"
    && rawComedogenicity.applicable !== false
    && (rawComedogenicity.ingredients?.length || 0) > 0
    ? rawComedogenicity
    : null
  const personal = userReport?.personal_compatibility ?? []
  const knownItems = personal.filter((item) => itemVerdict(item) !== "unknown")
  const unknownItems = personal.filter((item) => itemVerdict(item) === "unknown")
  const toggleItemInfo = (parameterId: string) => {
    setExpandedItems((current) => {
      const next = new Set(current)
      if (next.has(parameterId)) next.delete(parameterId)
      else next.add(parameterId)
      return next
    })
  }
  const productName = cleanProductName(
    userReport?.product_name || report?.product?.name || ""
  )
  const overall: EvaluationOverall = userReport?.overall ?? {
    verdict: "Недостаточно данных",
    tone: "muted",
    summary: "В сохранённом отчёте нет пользовательского вывода.",
    positive: 0,
    caution: 0,
    neutral: 0,
    negative: 0,
    unknown: 0,
    assessed: 0,
  }
  const sources = useMemo(() => {
    const urls = new Map<string, string>()
    const add = (url?: string, title?: string) => {
      const clean = (url || "").trim()
      if (!/^https?:\/\//i.test(clean) || urls.has(clean)) return
      urls.set(clean, (title || "").trim() || clean)
    }
    for (const url of userReport?.sources || []) add(url)
    for (const item of personal) {
      const rows = item.evidence?.length
        ? item.evidence
        : report?.evidence?.[item.parameter_id] ?? []
      for (const row of rows) add(row.source?.url, row.source?.title)
    }
    for (const row of primary?.basis ?? []) add(row.source)
    return Array.from(urls.entries()).map(([url, title]) => ({ url, title }))
  }, [personal, primary, report, userReport])

  if (!EVALUATION_V2_ENABLED || !enabled) return null

  if (restoring) {
    return (
      <div className="evalv2 evalv2--intro">
        <LoadingState label="Загружаем сохранённый результат" />
      </div>
    )
  }

  if (!started) {
    const actionLabel = restoreError
      ? "Повторить загрузку"
      : restoreReason
        ? "Обновить проверку"
        : "Проверить для меня"
    return (
      <div className="evalv2 evalv2--intro">
        <p className="eyebrow">Оценка продукта</p>
        {restoreError ? (
          <p className="evalv2__error" role="status">{restoreError}</p>
        ) : (
          <p className="evalv2__hint">
            {restoreReason || "Проверим основную функцию продукта и его совместимость с вашим профилем."}
          </p>
        )}
        <button
          type="button"
          className="evalv2__primary"
          onClick={() => {
            if (restoreError) setRestoreAttempt((value) => value + 1)
            else void start()
          }}
        >
          <span>{actionLabel}</span>
          {!restoreError && <span className="evalv2__credit">1 балл</span>}
        </button>
        {restoreError && restoreReason && (
          <button type="button" className="evalv2__secondary" onClick={() => void start()}>
            Обновить проверку
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="evalv2">
      {loading && <LoadingState label="Проверяем продукт" />}

      {notice && !loading && !report && (
        <p className="evalv2__empty">Не удалось подтвердить состав продукта.</p>
      )}

      {error && (
        <p className="evalv2__error" role="status">
          {error}
        </p>
      )}

      {primary && (
        <section className="evalv2__report">
          <ReportHeader productName={productName} overall={overall} />
          <FunctionLine
            item={primary}
            open={functionInfoOpen}
            onToggle={() => setFunctionInfoOpen((value) => !value)}
          />
          {comedogenicity && (
            <ComedogenicityLine
              item={comedogenicity}
              open={comedoOpen}
              onToggle={() => setComedoOpen((value) => !value)}
            />
          )}

          {knownItems.length > 0 && (
            <ol className="evalv2__verdicts">
              {knownItems.map((item, index) => (
                <VerdictRow
                  key={item.parameter_id}
                  item={item}
                  number={index + 1}
                  open={expandedItems.has(item.parameter_id)}
                  onToggle={() => toggleItemInfo(item.parameter_id)}
                />
              ))}
            </ol>
          )}

          {unknownItems.length > 0 && (
            <div className="evalv2__unknown">
              <p className="evalv2__unknown-title">Не удалось проверить</p>
              <ol className="evalv2__verdicts" start={knownItems.length + 1}>
                {unknownItems.map((item, index) => (
                  <VerdictRow
                    key={item.parameter_id}
                    item={item}
                    number={knownItems.length + index + 1}
                    open={expandedItems.has(item.parameter_id)}
                    onToggle={() => toggleItemInfo(item.parameter_id)}
                  />
                ))}
              </ol>
            </div>
          )}

          {personal.length === 0 && (
            <p className="evalv2__empty">
              Для вашего профиля нет подтверждённых персональных оценок.
            </p>
          )}

          {sources.length > 0 && (
            <div className="evalv2__sources">
              <button
                type="button"
                className="evalv2__sources-toggle"
                aria-expanded={sourcesOpen}
                onClick={() => setSourcesOpen((value) => !value)}
              >
                <span>Источники</span>
                <span className="evalv2__sources-count">{sources.length}</span>
              </button>
              {sourcesOpen && (
                <ul>
                  {sources.map((source) => (
                    <li key={source.url}>
                      <a href={source.url} target="_blank" rel="noreferrer">
                        {source.url}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}

      {!loading && !primary && !error && !notice && (
        <p className="evalv2__empty">Не удалось получить оценку продукта.</p>
      )}
    </div>
  )
}
