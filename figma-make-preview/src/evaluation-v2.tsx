// evaluation-v2.tsx — пользовательский результат Evaluation V2.
// Общий вердикт + основная функция + персональные пункты со значками.
// Технические статусы и средние баллы остаются в backend/snapshot; неизвестные
// пункты показываются нейтральным прочерком, а не положительной галочкой.
import { useEffect, useMemo, useState } from "react"
import {
  api,
  ApiError,
  EVALUATION_V2_ENABLED,
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

function VerdictIcon({ verdict }: { verdict?: string }) {
  const kind = verdict || "unknown"
  const glyph = kind === "positive" ? "✓" : kind === "negative" ? "✕" : "—"
  return (
    <span className={`evalv2__verdict-icon evalv2__verdict-icon--${kind}`} aria-hidden="true">
      {glyph}
    </span>
  )
}

function OverallCard({ overall }: { overall: EvaluationOverall }) {
  return (
    <article className={`evalv2__overall evalv2__overall--${overall.tone}`}>
      <p className="eyebrow">Общий вывод</p>
      <div className="evalv2__overall-main">
        <strong>{overall.verdict}</strong>
        <VerdictIcon verdict={overall.tone === "good" ? "positive" : overall.tone === "bad" ? "negative" : "neutral"} />
      </div>
      <p className="evalv2__overall-summary">{overall.summary}</p>
      <div className="evalv2__overall-counts" aria-label="Сводка проверенных пунктов">
        <span className="evalv2__count evalv2__count--positive">✓ {overall.positive} подходит</span>
        <span className="evalv2__count evalv2__count--neutral">— {overall.neutral} нейтрально</span>
        <span className="evalv2__count evalv2__count--negative">✕ {overall.negative} не подходит</span>
        <span className="evalv2__count evalv2__count--unknown">? {overall.unknown} нет данных</span>
      </div>
    </article>
  )
}

function PrimaryFunctionCard({ item }: { item: EvaluationPrimaryFunction }) {
  return (
    <article className="evalv2__function-card">
      <div className="evalv2__function-head">
        <div>
          <strong>{item.label}</strong>
          <p>{item.purpose}</p>
        </div>
      </div>
      {item.reason && (
        <details className="evalv2__explain">
          <summary>Почему так определена функция</summary>
          <p>{item.reason}</p>
          {item.score == null && item.label !== "Основная функция не определена" && (
            <p className="evalv2__function-note">
              Функция может быть определена по категории продукта; подтверждённость
              эффективности составом оценивается отдельно и не подменяется баллом.
            </p>
          )}
        </details>
      )}
      {(item.basis?.length ?? 0) > 0 && (
        <details className="evalv2__explain">
          <summary>Что учтено</summary>
          <ul className="evalv2__basis">
            {item.basis?.map((row) => (
              <li key={`${row.label}-${row.value}`}>
                <strong>{row.label}:</strong> {row.value}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}

function PersonalParameterCard({ item }: { item: EvaluationPersonalParameter }) {
  const intolerance = item.intolerance
  const verdict = item.verdict || (intolerance
    ? (intolerance.state === "present" ? "negative" : intolerance.state === "absent" ? "positive" : "unknown")
    : item.score != null && item.score >= 75 ? "positive" : item.score != null && item.score <= 25 ? "negative" : "neutral")
  return (
    <article className={`evalv2__parameter-card evalv2__parameter-card--${verdict}`}>
      <div className="evalv2__parameter-head">
        <div className="evalv2__verdict-title">
          <VerdictIcon verdict={verdict} />
          <div>
            <strong>{item.label || parameterLabel(item.parameter_id)}</strong>
            <small>{item.verdict_label || (verdict === "unknown" ? "Не удалось определить" : "По вашему профилю")}</small>
          </div>
        </div>
      </div>
      {item.reason && (
        <details className="evalv2__explain">
          <summary>Почему такой вывод</summary>
          <p>{item.reason}</p>
          {intolerance?.reason && <p className="evalv2__intolerance-note">{intolerance.reason}</p>}
        </details>
      )}
    </article>
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
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
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
          setRestoreReason("Не удалось загрузить сохранённый отчёт. Обновите проверку.")
        }
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => { cancelled = true }
  }, [productId, profileKey, enabled, canRestore])

  const start = async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setStarted(true)
    onStarted?.()
    setLoading(true)
    setError("")
    setNotice("")
    setRestoreReason("")
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
      } else {
        setError("Не удалось проверить продукт. Попробуйте позже.")
      }
    } finally {
      setLoading(false)
    }
  }

  const userReport = report?.user_report
  const primary = userReport?.primary_function ?? report?.primary_function ?? null
  const personal = userReport?.personal_compatibility ?? []
  const productName = cleanProductName(
    userReport?.product_name || report?.product?.name || ""
  )
  const overall: EvaluationOverall = userReport?.overall ?? {
    verdict: "Недостаточно данных",
    tone: "muted",
    summary: "В сохранённом отчёте нет пользовательского вывода.",
    positive: 0,
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
      <div className="evalv2 evalv2--intro" role="status">
        <div className="evalv2__loading">
          <img src="/loading.gif" alt="" />
          <span>Загружаем сохранённый результат…</span>
        </div>
      </div>
    )
  }

  if (!started) {
    return (
      <div className="evalv2 evalv2--intro">
        <p className="eyebrow">Оценка продукта</p>
        <p className="evalv2__hint">
          {restoreReason || "Проверим основную функцию продукта и его совместимость с вашим профилем."}
        </p>
        <button type="button" className="evalv2__primary" onClick={() => void start()}>
          <span><span aria-hidden="true">✦</span> {restoreReason ? "Обновить проверку" : "Проверить для меня"}</span>
          <small className="evalv2__credit"><span aria-hidden="true">◈</span> AI · 1 балл</small>
        </button>
      </div>
    )
  }

  return (
    <div className="evalv2">
      {loading && (
        <div className="evalv2__loading" role="status">
          <img src="/loading.gif" alt="" />
          <span>Проверяем продукт…</span>
        </div>
      )}

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
          <div className="evalv2__product-head">
            <p className="eyebrow">Результат проверки</p>
            {productName && <h4 className="evalv2__product-name">{productName}</h4>}
          </div>
          <OverallCard overall={overall} />
          <p className="evalv2__section-label">Основная функция</p>
          <PrimaryFunctionCard item={primary} />

          <section className="evalv2__compatibility">
            <h4>Персональная совместимость</h4>
            {personal.length > 0 ? (
              personal.map((item) => (
                <PersonalParameterCard key={item.parameter_id} item={item} />
              ))
            ) : (
              <p className="evalv2__empty">
                Для вашего профиля нет подтверждённых персональных оценок.
              </p>
            )}
            {sources.length > 0 && (
              <details className="evalv2__sources">
                <summary>Источники</summary>
                <ul>
                  {sources.map((source) => (
                    <li key={source.url}>
                      <a href={source.url} target="_blank" rel="noreferrer">
                        {source.url}
                      </a>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        </section>
      )}

      {!loading && !primary && !error && !notice && (
        <p className="evalv2__empty">Не удалось получить оценку продукта.</p>
      )}
    </div>
  )
}
