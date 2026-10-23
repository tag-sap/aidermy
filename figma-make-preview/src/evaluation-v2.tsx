// evaluation-v2.tsx — компактная панель Evaluation V2 внутри существующего drawer.
// Ничего не заменяет: показывает независимую оценку по параметрам и честный статус
// готовности. Включается флагом VITE_EVALUATION_V2=1 на сервере, где развёрнут V2.
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  api,
  ApiError,
  EVALUATION_V2_ENABLED,
  type EvaluationAnalysis,
  type EvaluationCompositionState,
  type EvaluationEvidence,
  type EvaluationProductStatus,
  type EvaluationReport,
} from "./api"

const STATUS_LABEL: Record<string, string> = {
  complete: "Анализ завершён",
  incomplete: "Анализ не завершён",
  failed: "Техническая ошибка исследования",
  blocked: "Нужен пригодный состав",
}

const GAP_LABEL: Record<string, string> = {
  missing: "нет результата",
  stale: "результат устарел",
  insufficient: "недостаточно доказательств",
  unsupported: "непригодный статус",
}

const SECTION_LABEL: Record<string, string> = {
  skin_type: "Тип кожи",
  problem: "Проблема",
  goal: "Цель",
  intolerance: "Непереносимость",
  therapy: "Терапия",
  procedure: "Процедура",
  ingredient: "Ингредиент",
  age: "Возраст",
}

function parameterLabel(parameterId: string): string {
  const [section, ...rest] = parameterId.split(":")
  const title = SECTION_LABEL[section] || section
  const value = rest.join(":").replace(/_/g, " ").trim()
  return value ? `${title}: ${value}` : title
}

function shortText(text: string, limit = 220): string {
  const clean = (text || "").replace(/\s+/g, " ").trim()
  return clean.length > limit ? `${clean.slice(0, limit)}…` : clean
}

function statusTone(status: string): string {
  if (status === "complete") return "evalv2__badge--ok"
  if (status === "failed") return "evalv2__badge--bad"
  if (status === "blocked") return "evalv2__badge--muted"
  return "evalv2__badge--warn"
}

export function EvaluationV2Panel({
  productId,
  profile,
  enabled = true,
}: {
  productId: number
  profile: Record<string, unknown>
  enabled?: boolean
}) {
  const [status, setStatus] = useState<EvaluationProductStatus | null>(null)
  const [report, setReport] = useState<EvaluationReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [compositionNotice, setCompositionNotice] = useState("")
  const [error, setError] = useState("")
  const [unavailable, setUnavailable] = useState(false)
  const profileKey = useMemo(() => JSON.stringify(profile || {}), [profile])

  const load = useCallback(async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setLoading(true)
    setError("")
    try {
      const data = await api.evaluationProductStatus(productId, JSON.parse(profileKey))
      setStatus(data)
      setUnavailable(false)
    } catch (e) {
      const statusCode = e instanceof ApiError ? e.status : 0
      if (statusCode === 401) {
        setError("Войдите, чтобы увидеть оценку состава V2.")
      } else if (statusCode === 404 || statusCode === 503) {
        setUnavailable(true)
      } else {
        setError(e instanceof Error ? e.message : "Не удалось получить статус анализа V2.")
      }
    } finally {
      setLoading(false)
    }
  }, [enabled, productId, profileKey])

  useEffect(() => {
    void load()
  }, [load])

  const [stage, setStage] = useState<"idle" | "composition" | "parameters" | "evaluating" | "done">("idle")

  const checkProduct = async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setLoading(true)
    setError("")
    setCompositionNotice("")
    setReport(null)
    setStage("composition")
    try {
      const checked = await api.evaluationCompositionCheck(productId)
      setCompositionNotice(checked.message || "")
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              composition: checked.composition,
              composition_state: checked.composition_state,
            }
          : prev
      )
      if (!checked.composition_state?.usable) {
        // Нет пригодного состава: не изображаем анализ и не запускаем LLM.
        setStage("idle")
        return
      }
      setStage("parameters")
      const data = await api.evaluationProductAnalyze(productId, JSON.parse(profileKey))
      setStage("evaluating")
      setReport(data)
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              analysis: data.analysis,
              composition: data.composition,
              composition_state: data.composition_state,
            }
          : prev
      )
      setStage("done")
    } catch (e) {
      const statusCode = e instanceof ApiError ? e.status : 0
      if (statusCode === 401) {
        setError("Войдите, чтобы проверить продукт.")
      } else if (statusCode === 503) {
        setError("Проверка недоступна: сервер не настроен для анализа состава.")
      } else {
        setError(e instanceof Error ? e.message : "Не удалось проверить продукт.")
      }
      setStage("idle")
    } finally {
      setLoading(false)
    }
  }

  if (!EVALUATION_V2_ENABLED || !enabled || unavailable) return null

  const analysis: EvaluationAnalysis | null = report?.analysis ?? status?.analysis ?? null
  const total = report?.snapshot?.total ?? null
  const parameters = report?.snapshot?.parameters ?? []
  const sources =
    (analysis?.documents_fetched ?? 0) + (analysis?.documents_reused ?? 0)
  const assessedCount = analysis?.assessed_parameters.length ?? 0
  const gapIds = new Set((analysis?.gaps ?? []).map((gap) => gap.parameter_id))
  const failedOnly = (analysis?.failed_parameters ?? []).filter((pid) => !gapIds.has(pid))
  const compositionState: EvaluationCompositionState | null =
    report?.composition_state ?? status?.composition_state ?? null
  const composition = report?.composition ?? status?.composition ?? null
  const canEvaluate = compositionState ? compositionState.usable : true
  const compositionBadge = compositionState?.usable
    ? compositionState.reason === "trusted_catalog"
      ? "состав пригоден · доверенный источник"
      : "состав подтверждён"
    : "нужна проверка состава"
  const reportDate =
    report?.snapshot?.created_at && !Number.isNaN(Date.parse(report.snapshot.created_at))
      ? new Date(report.snapshot.created_at).toLocaleString("ru-RU", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : ""
  const evidenceFor = (parameterId: string): EvaluationEvidence[] =>
    report?.evidence?.[parameterId] ?? []


  return (
    <div className="evalv2">
      <div className="evalv2__head">
        <div>
          <p className="eyebrow">Оценка состава · V2</p>
          <p className="evalv2__hint">
            Независимая оценка по каждому пункту анкеты. Вердикт отключён до калибровки.
          </p>
        </div>
        <button
          type="button"
          className="evalv2__refresh"
          onClick={() => void checkProduct()}
          disabled={loading}
        >
          {loading ? "Проверяем…" : report ? "Проверить снова" : "Проверить продукт"}
        </button>
      </div>

      {loading && (
        <div className="evalv2__stages" aria-live="polite">
          <span className={stage === "composition" ? "is-active" : stage === "idle" ? "" : "is-done"}>
            Проверка состава
          </span>
          <span className={stage === "parameters" ? "is-active" : stage === "evaluating" || stage === "done" ? "is-done" : ""}>
            Подготовка параметров
          </span>
          <span className={stage === "evaluating" ? "is-active" : stage === "done" ? "is-done" : ""}>
            Оценка параметров
          </span>
          <span className={stage === "done" ? "is-done" : ""}>Формирование результата</span>
        </div>
      )}

      <div className="evalv2__composition">
        <div className="evalv2__composition-head">
          <span>Состав</span>
          <span className={`evalv2__badge ${canEvaluate ? "evalv2__badge--ok" : "evalv2__badge--warn"}`}>
            {compositionBadge}
          </span>
        </div>
        {composition?.inci_raw ? (
          <p className="evalv2__inci">{composition.inci_raw}</p>
        ) : (
          <p className="evalv2__empty">В карточке товара нет сохранённого состава.</p>
        )}
        <p className="evalv2__composition-note">
          {compositionNotice || compositionState?.message || "Состав будет проверен по кнопке «Проверить продукт»."}
        </p>
        {composition?.source && (
          <p className="evalv2__source">
            Источник: {compositionState?.source_host || composition.source}
          </p>
        )}
      </div>

      {report && (
        <div className="evalv2__report-meta">
          <strong>{report.product.name}</strong>
          {reportDate && <span> · проверено {reportDate}</span>}
        </div>
      )}

      {analysis && (
        <>
          <div className="evalv2__status">
            <span className={`evalv2__badge ${statusTone(analysis.status)}`}>
              {STATUS_LABEL[analysis.status] || analysis.status}
            </span>
            {total != null && <span className="evalv2__total">{total.toFixed(2)} / 100</span>}
            {sources > 0 && <span className="evalv2__meta">источников: {sources}</span>}
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

          {total == null && analysis.status !== "blocked" && assessedCount === 0 && (
            <p className="evalv2__empty">
              Нет ни одной подтверждённой оценки: недостаток данных не заменяется баллом.
            </p>
          )}

          {total == null && analysis.status !== "blocked" && assessedCount > 0 && (
            <p className="evalv2__empty">
              Оценки готовы. Нажмите «Проверить продукт», чтобы увидеть баллы и обоснования.
            </p>
          )}

          {parameters.length > 0 && (
            <ul className="evalv2__list">
              {parameters.map((row) => {
                const evidence = evidenceFor(row.parameter_id)
                return (
                  <li key={row.parameter_id} className="evalv2__item">
                    <div className="evalv2__item-head">
                      <span>{parameterLabel(row.parameter_id)}</span>
                      <b>{row.value}</b>
                    </div>
                    <p>{shortText(row.reason)}</p>
                    {evidence.length > 0 && (
                      <details className="evalv2__evidence">
                        <summary>Доказательства ({evidence.length})</summary>
                        <ul>
                          {evidence.slice(0, 5).map((item) => (
                            <li key={item.id}>
                              <p>«{shortText(item.quote, 180)}»</p>
                              <span>{item.claim}</span>
                              {item.source?.url && (
                                <a href={item.source.url} target="_blank" rel="noreferrer">
                                  {item.source.url}
                                </a>
                              )}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </li>
                )
              })}
            </ul>
          )}

          {analysis.gaps.length > 0 && (
            <div className="evalv2__gaps">
              <p className="evalv2__gaps-title">Неоценённые параметры</p>
              <ul>
                {analysis.gaps.slice(0, 6).map((gap) => (
                  <li key={gap.parameter_id}>
                    <span>{parameterLabel(gap.parameter_id)}</span>
                    <em>{GAP_LABEL[gap.reason] || gap.reason}</em>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {failedOnly.length > 0 && (
            <div className="evalv2__gaps">
              <p className="evalv2__gaps-title">Неоценённые параметры: техническая ошибка</p>
              <ul>
                {failedOnly.slice(0, 6).map((parameterId) => (
                  <li key={parameterId}>
                    <span>{parameterLabel(parameterId)}</span>
                    <em>ошибка исследования</em>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analysis.status === "blocked" && (
            <p className="evalv2__empty">
              {compositionState?.message ||
                "Состав не готов к оценке: проверьте его происхождение и полноту."}
            </p>
          )}

          {analysis.notes.length > 0 && (
            <p className="evalv2__note">
              {shortText(analysis.notes[analysis.notes.length - 1], 260)}
            </p>
          )}
        </>
      )}

      {!analysis && !loading && !error && (
        <p className="evalv2__empty">Загружаем статус анализа…</p>
      )}
      {error && (
        <p className="evalv2__error" role="status">
          {error}
        </p>
      )}
    </div>
  )
}

