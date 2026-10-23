// evaluation-v2.tsx — пользовательский результат Evaluation V2.
// Две независимые части: основная функция продукта и персональная совместимость.
// Технические статусы, средние баллы и список непроверенных пунктов здесь не
// показываются; они остаются в backend/snapshot для диагностики.
import { useMemo, useState } from "react"
import {
  api,
  ApiError,
  EVALUATION_V2_ENABLED,
  type EvaluationEvidence,
  type EvaluationPersonalParameter,
  type EvaluationPrimaryFunction,
  type EvaluationReport,
} from "./api"

const VALUE_LABEL: Record<string, string> = {
  "skin_type:dry": "Сухая кожа",
  "skin_type:oily": "Жирная кожа",
  "skin_type:normal": "Нормальная кожа",
  "skin_type:combination": "Комбинированная кожа",
  "problem:dryness": "Сухость и обезвоженность",
  "problem:acne_general": "Склонность к акне",
  "problem:acne": "Склонность к акне",
  "goal:hydration": "Цель: увлажнение",
  "goal:acne": "Цель: уменьшить акне",
  "intolerance:niacinamide_intolerance": "Непереносимость ниацинамида",
  "intolerance:fragrance_intolerance": "Непереносимость отдушек",
  "intolerance:alcohol_intolerance": "Непереносимость спирта",
  "intolerance:acid_intolerance": "Непереносимость кислот",
  "intolerance:retinoid_intolerance": "Непереносимость ретиноидов",
  "therapy:adapalene": "Использование адапалена",
  "therapy:antibiotic": "Антибактериальная терапия",
  "therapy:benzoyl_peroxide": "Использование бензоилпероксида",
  "therapy:tretinoin": "Использование третиноина",
  "therapy:acid_therapy": "Кислотная терапия",
  "procedure:recent_biorevitalization@<7": "Биоревитализация: первые 7 дней",
  "procedure:recent_laser@<7": "Лазерная процедура: первые 7 дней",
  "procedure:recent_peeling@<7": "Пилинг: первые 7 дней",
}

function parameterLabel(parameterId: string): string {
  // The backend snapshot now carries a normal Russian label. Never fall back to
  // a machine id when an older snapshot is opened.
  return VALUE_LABEL[parameterId] || "Параметр профиля"
}

function shortText(text: string, limit = 300): string {
  const clean = (text || "").replace(/\s+/g, " ").trim()
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean
}

function cleanProductName(name: string): string {
  return (name || "").replace(/\s+/g, " ").trim()
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(Number(value))))
}



function ScoreBar({ score }: { score: number }) {
  return (
    <>
      <div className="evalv2__track" role="img" aria-label={`Оценка ${score} из 100`}>
        <div className="evalv2__fill" style={{ width: `${score}%` }} />
      </div>
      <div className="evalv2__ticks" aria-hidden="true">
        <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
      </div>
    </>
  )
}

function PrimaryFunctionCard({ item }: { item: EvaluationPrimaryFunction }) {
  const score = item.score == null ? null : clampScore(item.score)
  return (
    <article className="evalv2__function-card">
      <div className="evalv2__function-head">
        <div>
          <strong>{item.label}</strong>
          <p>{item.purpose}</p>
        </div>
        {score != null && (
          <span className="evalv2__function-score">
            {score}<small>/100</small>
          </span>
        )}
      </div>
      {score != null && <ScoreBar score={score} />}
      {item.reason && <p className="evalv2__reason">{shortText(item.reason, 260)}</p>}
      {(item.basis?.length ?? 0) > 0 && (
        <details className="evalv2__explain">
          <summary>Что учтено</summary>
          <ul className="evalv2__basis">
            {item.basis?.map((row) => (
              <li key={`${row.label}-${row.value}`}>
                <strong>{row.label}:</strong> {shortText(row.value, 180)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}

function PersonalParameterCard({
  item,
  evidence,
}: {
  item: EvaluationPersonalParameter
  evidence: EvaluationEvidence[]
}) {
  const score = clampScore(item.score)
  return (
    <article className="evalv2__parameter-card">
      <div className="evalv2__parameter-head">
        <div>
          <strong>{item.label || parameterLabel(item.parameter_id)}</strong>
          <small>По вашему профилю</small>
        </div>
        <span className="evalv2__parameter-score">
          {score}<small>/100</small>
        </span>
      </div>
      <ScoreBar score={score} />
      <p className="evalv2__reason">{shortText(item.reason, 260)}</p>
      {evidence.length > 0 && (
        <details className="evalv2__explain">
          <summary>Источники</summary>
          <div className="evalv2__evidence">
            <ul>
              {evidence.slice(0, 5).map((source) => (
                <li key={source.id}>
                  <p>«{shortText(source.quote, 220)}»</p>
                  {source.claim && <span>{source.claim}</span>}
                  {source.source?.url && (
                    <a href={source.source.url} target="_blank" rel="noreferrer">
                      {source.source.url}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </article>
  )
}

export function EvaluationV2Panel({
  productId,
  profile,
  enabled = true,
  onStarted,
}: {
  productId: number
  profile: Record<string, unknown>
  enabled?: boolean
  onStarted?: () => void
}) {
  const [started, setStarted] = useState(false)
  const [report, setReport] = useState<EvaluationReport | null>(null)
  const [notice, setNotice] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const profileKey = useMemo(() => JSON.stringify(profile || {}), [profile])

  const start = async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setStarted(true)
    onStarted?.()
    setLoading(true)
    setError("")
    setNotice("")
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

  if (!EVALUATION_V2_ENABLED || !enabled) return null

  if (!started) {
    return (
      <div className="evalv2 evalv2--intro">
        <p className="eyebrow">Оценка продукта</p>
        <p className="evalv2__hint">
          Проверим основную функцию продукта и его совместимость с вашим профилем.
        </p>
        <button type="button" className="evalv2__primary" onClick={() => void start()}>
          Проверить для меня
        </button>
      </div>
    )
  }

  const userReport = report?.user_report
  const primary = userReport?.primary_function ?? report?.primary_function ?? null
  const personal = userReport?.personal_compatibility ?? []
  const productName = cleanProductName(
    userReport?.product_name || report?.product?.name || ""
  )

  return (
    <div className="evalv2">
      {loading && <p className="evalv2__empty">Проверяем продукт…</p>}

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
            <p className="eyebrow">Основная функция</p>
            {productName && <h4 className="evalv2__product-name">{productName}</h4>}
          </div>
          <PrimaryFunctionCard item={primary} />

          <section className="evalv2__compatibility">
            <h4>Персональная совместимость</h4>
            {personal.length > 0 ? (
              personal.map((item) => (
                <PersonalParameterCard
                  key={item.parameter_id}
                  item={item}
                  evidence={
                    item.evidence?.length
                      ? item.evidence
                      : report?.evidence?.[item.parameter_id] ?? []
                  }
                />
              ))
            ) : (
              <p className="evalv2__empty">
                Для вашего профиля нет подтверждённых персональных оценок.
              </p>
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
