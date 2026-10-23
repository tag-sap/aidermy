// evaluation-v2.tsx — пользовательская карточка оценки Evaluation V2.
// До нажатия показывает только одно действие; после — реальные оценки,
// шкалы и раскрываемые объяснения. Никаких демонстрационных баллов.
import { useMemo, useState } from "react"
import {
  api,
  ApiError,
  EVALUATION_V2_ENABLED,
  type EvaluationAnalysis,
  type EvaluationCompositionState,
  type EvaluationEvidence,
  type EvaluationReport,
} from "./api"

const SECTION_LABEL: Record<string, string> = {
  skin_type: "Тип кожи",
  problem: "Проблема кожи",
  goal: "Цель ухода",
  intolerance: "Непереносимость",
  therapy: "Текущая терапия",
  procedure: "Процедура",
  ingredient: "Ингредиент",
  age: "Возраст",
}

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

const GAP_LABEL: Record<string, string> = {
  missing: "нужны данные",
  stale: "результат устарел",
  insufficient: "недостаточно доказательств",
  unsupported: "нужна повторная проверка",
}

const STATUS_TEXT: Record<string, string> = {
  complete: "Готово",
  incomplete: "Незавершённая оценка",
  failed: "Не удалось завершить",
  blocked: "Нужны данные о составе",
}

function parameterLabel(parameterId: string): string {
  if (VALUE_LABEL[parameterId]) return VALUE_LABEL[parameterId]
  const [section, ...rest] = parameterId.split(":")
  const title = SECTION_LABEL[section] || "Параметр профиля"
  const value = rest.join(":").replace(/_/g, " ").trim()
  return value ? `${title}: ${value}` : title
}

function shortText(text: string, limit = 240): string {
  const clean = (text || "").replace(/\s+/g, " ").trim()
  return clean.length > limit ? `${clean.slice(0, limit)}…` : clean
}

function formatDate(value?: string): string {
  if (!value || Number.isNaN(Date.parse(value))) return ""
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
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
  const [compositionState, setCompositionState] =
    useState<EvaluationCompositionState | null>(null)
  const [notice, setNotice] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [stage, setStage] = useState<"idle" | "composition" | "evaluation">("idle")
  const profileKey = useMemo(() => JSON.stringify(profile || {}), [profile])

  const start = async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setStarted(true)
    onStarted?.()
    setLoading(true)
    setError("")
    setNotice("")
    setReport(null)
    setCompositionState(null)
    setStage("composition")
    try {
      const checked = await api.evaluationCompositionCheck(productId)
      setNotice(checked.message || "")
      setCompositionState(checked.composition_state)
      if (!checked.composition_state?.usable) {
        setStage("idle")
        return
      }
      setStage("evaluation")
      const data = await api.evaluationProductEvaluate(
        productId,
        JSON.parse(profileKey)
      )
      setReport(data)
      setStage("idle")
    } catch (e) {
      const statusCode = e instanceof ApiError ? e.status : 0
      if (statusCode === 401) {
        setError("Войдите, чтобы проверить продукт.")
      } else if (statusCode === 503) {
        setError("Проверка временно недоступна: сервер не готов к анализу.")
      } else {
        setError(e instanceof Error ? e.message : "Не удалось проверить продукт.")
      }
      setStage("idle")
    } finally {
      setLoading(false)
    }
  }

  if (!EVALUATION_V2_ENABLED || !enabled) return null

  if (!started) {
    return (
      <div className="evalv2 evalv2--intro">
        <p className="eyebrow">Персональная оценка</p>
        <p className="evalv2__hint">
          Проверим состав по вашим ответам о коже и покажем, что подтверждено
          источниками, а что осталось неизвестным.
        </p>
        <button type="button" className="evalv2__primary" onClick={() => void start()}>
          Проверить для меня
        </button>
      </div>
    )
  }

  const analysis: EvaluationAnalysis | null = report?.analysis ?? null
  const total = report?.snapshot?.total ?? null
  const parameters = report?.snapshot?.parameters ?? []
  const assessedCount = analysis?.assessed_parameters.length ?? 0
  const gapIds = new Set((analysis?.gaps ?? []).map((gap) => gap.parameter_id))
  const failedOnly = (analysis?.failed_parameters ?? []).filter((id) => !gapIds.has(id))
  const evidenceFor = (parameterId: string): EvaluationEvidence[] =>
    report?.evidence?.[parameterId] ?? []
  const reportDate = formatDate(report?.snapshot?.created_at)

  return (
    <div className="evalv2">
      <div className="evalv2__head">
        <div>
          <p className="eyebrow">Персональная оценка</p>
          <p className="evalv2__hint">
            Оценка по применимым пунктам анкеты. Вердикт отключён до калибровки.
          </p>
        </div>
        <button
          type="button"
          className="evalv2__refresh"
          onClick={() => void start()}
          disabled={loading}
        >
          {loading ? "Проверяем…" : report ? "Проверить снова" : "Проверить для меня"}
        </button>
      </div>

      {loading && (
        <div className="evalv2__stages" aria-live="polite">
          <span className={stage === "composition" ? "is-active" : ""}>
            Проверка состава
          </span>
          <span className={stage === "evaluation" ? "is-active" : ""}>
            Исследование и оценка параметров
          </span>
        </div>
      )}

      {notice && !loading && !compositionState?.usable && (
        <p className="evalv2__empty">{shortText(notice, 360)}</p>
      )}

      {error && (
        <p className="evalv2__error" role="status">
          {error}
        </p>
      )}

      {analysis && (
        <>
          <div className="evalv2__status">
            <span className={`evalv2__badge ${
              analysis.status === "complete"
                ? "evalv2__badge--ok"
                : analysis.status === "failed"
                  ? "evalv2__badge--bad"
                  : "evalv2__badge--warn"
            }`}>
              {STATUS_TEXT[analysis.status] || "Оценка"}
            </span>
            {total != null && <span className="evalv2__total">{total.toFixed(2)} / 100</span>}
            {reportDate && <span className="evalv2__meta">проверено {reportDate}</span>}
          </div>

          {total != null && (
            <p className="evalv2__score-note">
              Среднее по {assessedCount} оценённым параметрам. Это не вероятность
              эффективности и не медицинская рекомендация.
            </p>
          )}

          <p className="evalv2__summary">
            Оценено: {assessedCount} · не оценено: {analysis.gaps.length + failedOnly.length}
          </p>

          {total == null && assessedCount === 0 && (
            <p className="evalv2__empty">
              Нет ни одной подтверждённой оценки. Недостаток данных не заменяется баллом.
            </p>
          )}



          {parameters.map((row) => {
            const evidence = evidenceFor(row.parameter_id)
            const score = Math.max(0, Math.min(100, Number(row.value)))
            return (
              <article className="evalv2__parameter-card" key={row.parameter_id}>
                <div className="evalv2__parameter-head">
                  <div>
                    <strong>{parameterLabel(row.parameter_id)}</strong>
                    <small>Оценка по вашему профилю</small>
                  </div>
                  <span className="evalv2__parameter-score">
                    {Math.round(score)}<small>/100</small>
                  </span>
                </div>
                <div className="evalv2__track" role="img" aria-label={`Оценка ${Math.round(score)} из 100`}>
                  <div className="evalv2__fill" style={{ width: `${score}%` }} />
                </div>
                <div className="evalv2__ticks" aria-hidden="true">
                  <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
                </div>
                <details className="evalv2__explain">
                  <summary>Почему такая оценка</summary>
                  <p>{row.reason}</p>
                  {evidence.length > 0 && (
                    <div className="evalv2__evidence">
                      <p className="evalv2__evidence-title">Что подтверждает оценку</p>
                      <ul>
                        {evidence.slice(0, 5).map((item) => (
                          <li key={item.id}>
                            <p>«{shortText(item.quote, 240)}»</p>
                            {item.claim && <span>{item.claim}</span>}
                            {item.source?.url && (
                              <a href={item.source.url} target="_blank" rel="noreferrer">
                                {item.source.url}
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </details>
              </article>
            )
          })}

          {(analysis.gaps.length > 0 || failedOnly.length > 0) && (
            <div className="evalv2__unassessed">
              <h4>Что осталось непроверенным</h4>
              <ul>
                {analysis.gaps.map((gap) => (
                  <li key={gap.parameter_id}>
                    <span>{parameterLabel(gap.parameter_id)}</span>
                    <em>{GAP_LABEL[gap.reason] || "требует проверки"}</em>
                  </li>
                ))}
                {failedOnly.map((parameterId) => (
                  <li key={`failed-${parameterId}`}>
                    <span>{parameterLabel(parameterId)}</span>
                    <em>техническая ошибка исследования</em>
                  </li>
                ))}
              </ul>
              <p className="evalv2__note">
                {analysis.status === "incomplete"
                  ? "Отчёт неполный: часть параметров пока не имеет подтверждённых данных."
                  : "Эти пункты не участвуют в итоговой оценке."}
              </p>
            </div>
          )}

          {analysis.notes.length > 0 && (
            <p className="evalv2__note">{shortText(analysis.notes[analysis.notes.length - 1], 320)}</p>
          )}
        </>
      )}

      {!loading && !report && !error && !notice && (
        <p className="evalv2__empty">Готовим оценку…</p>
      )}
    </div>
  )
}
