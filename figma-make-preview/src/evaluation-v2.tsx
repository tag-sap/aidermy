// evaluation-v2.tsx - пользовательский результат Evaluation V2.
// Общий вердикт + основная функция + персональные пункты со значками.
// Технические статусы и средние баллы остаются в backend/snapshot; неизвестные
// пункты показываются нейтральным прочерком, а не положительной галочкой.
import { useEffect, useMemo, useState } from "react"
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
  // Older saved reports use glyph names; normalize them to the same sprite.
  check: "happy",
  cross: "dead",
  dash: "neutral",
}

function iconName(verdict?: string, icon?: string): string {
  const value = icon || VERDICT_ICON_BY_STATUS[verdict || ""] || "neutral"
  return ["dead", "happy", "neutral", "alert"].includes(value) ? value : "neutral"
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
  return (
    <span className={`evalv2__verdict-icon evalv2__verdict-icon--${name} ${className}`.trim()} aria-hidden="true">
      <svg viewBox="5 5 130 215" focusable="false">
        <use href={`/icons/verdict_icons.svg#verdict-${name}`} />
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
        <span className="evalv2__overall-verdict-wrap">
          <VerdictIcon verdict={overall.tone === "bad" ? "negative" : overall.tone === "good" ? "positive" : overall.tone === "warn" ? "caution" : "neutral"} icon={overall.icon} className="evalv2__overall-icon" />
          <strong className={`evalv2__overall-verdict evalv2__overall-verdict--${overall.tone}`}>
            {overall.verdict}
          </strong>
        </span>
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
