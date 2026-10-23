// evaluation-v2.tsx — компактная панель Evaluation V2 внутри существующего drawer.
// Ничего не заменяет: показывает независимую оценку по параметрам и честный статус
// готовности. Включается флагом VITE_EVALUATION_V2=1 на сервере, где развёрнут V2.
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  api,
  ApiError,
  EVALUATION_V2_ENABLED,
  type EvaluationAnalysis,
  type EvaluationProductStatus,
  type EvaluationReport,
} from "./api"

const STATUS_LABEL: Record<string, string> = {
  complete: "Анализ завершён",
  incomplete: "Анализ не завершён",
  failed: "Техническая ошибка исследования",
  blocked: "Нужен подтверждённый состав",
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

  const recalculate = async () => {
    if (!EVALUATION_V2_ENABLED || !enabled) return
    setLoading(true)
    setError("")
    try {
      const data = await api.evaluationProductAnalyze(productId, JSON.parse(profileKey))
      setReport(data)
      setStatus((prev) =>
        prev ? { ...prev, analysis: data.analysis, composition: data.composition } : prev
      )
    } catch (e) {
      const statusCode = e instanceof ApiError ? e.status : 0
      if (statusCode === 503) {
        setError("Анализ V2 недоступен: сервер не настроен для исследования.")
      } else {
        setError(e instanceof Error ? e.message : "Не удалось выполнить анализ V2.")
      }
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
          onClick={() => void recalculate()}
          disabled={loading}
        >
          {loading ? "…" : "Обновить"}
        </button>
      </div>

      {analysis && (
        <>
          <div className="evalv2__status">
            <span className={`evalv2__badge ${statusTone(analysis.status)}`}>
              {STATUS_LABEL[analysis.status] || analysis.status}
            </span>
            {total != null && <span className="evalv2__total">{total.toFixed(2)} / 100</span>}
            {sources > 0 && <span className="evalv2__meta">источников: {sources}</span>}
          </div>

          {total == null && analysis.status !== "blocked" && assessedCount === 0 && (
            <p className="evalv2__empty">
              Нет ни одной подтверждённой оценки: недостаток данных не заменяется баллом.
            </p>
          )}

          {total == null && analysis.status !== "blocked" && assessedCount > 0 && (
            <p className="evalv2__empty">
              Оценки готовы. Нажмите «Обновить», чтобы увидеть баллы и обоснования.
            </p>
          )}

          {parameters.length > 0 && (
            <ul className="evalv2__list">
              {parameters.map((row) => (
                <li key={row.parameter_id} className="evalv2__item">
                  <div className="evalv2__item-head">
                    <span>{parameterLabel(row.parameter_id)}</span>
                    <b>{row.value}</b>
                  </div>
                  <p>{shortText(row.reason)}</p>
                </li>
              ))}
            </ul>
          )}

          {analysis.gaps.length > 0 && (
            <div className="evalv2__gaps">
              <p className="evalv2__gaps-title">Что осталось непроверенным</p>
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

          {analysis.status === "blocked" && (
            <p className="evalv2__empty">
              Состав ещё не подтверждён: администратор должен подтвердить INCI, после этого
              анализ запустится.
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

