import type { ReportDetail, ReportIngredient } from "./api"

function IngredientDetails({ item }: { item: ReportIngredient }) {
  return (
    <details className="report-ingredient">
      <summary>
        <span>{item.name}</span>
        {item.unknown
          ? <span className="report-ingredient__tag">нет данных</span>
          : item.direction === "negative"
            ? <span className="report-ingredient__tag report-ingredient__tag--warn">внимание</span>
            : item.direction === "positive"
              ? <span className="report-ingredient__tag report-ingredient__tag--good">в пользу</span>
              : null}
      </summary>
      <div className="report-ingredient__body">
        <p><strong>Функция:</strong> {item.function || "нет подтверждённого описания"}</p>
        {item.skin_effects && <p><strong>Действие по данным базы:</strong> {item.skin_effects}</p>}
        <p><strong>Роль в отчёте:</strong> {item.role || "входит в состав продукта"}</p>
        <p className="report-ingredient__meta">
          Источник: {item.unknown ? "подтверждённых данных нет" : `база знаний ингредиентов, evidence=${item.evidence_level || "не указан"}`}
          {item.sources ? ` · ${item.sources}` : ""}
        </p>
      </div>
    </details>
  )
}

export function ReportDetails({ details }: { details: ReportDetail }) {
  const quality = details.data_quality
  const sections = details.sections || []
  const key = details.key_ingredients || []
  const other = details.other_ingredients || []
  if (!sections.length && !key.length && !other.length) return null
  return (
    <div className="report-details">
      {quality && (
        <p className="report-details__quality">
          Качество данных: <strong>{quality.label || "не определено"}</strong>
          {typeof quality.coverage === "number" ? ` · покрытие ${Math.round(quality.coverage * 100)}%` : ""}
          {typeof quality.confidence === "number" ? ` · уверенность ${Math.round(quality.confidence * 100)}%` : ""}
        </p>
      )}
      {sections.map((section) => (
        <details className="report-detail" key={section.id}>
          <summary>
            <span>{section.title}</span>
            {section.basis && <small>{section.basis}</small>}
          </summary>
          <div className="report-detail__body">
            {(section.paragraphs || []).map((paragraph, index) => (
              <p key={index}>{paragraph}</p>
            ))}
          </div>
        </details>
      ))}
      {key.length > 0 && (
        <details className="report-detail" open>
          <summary><span>Ключевые ингредиенты</span><small>почему они важны для результата</small></summary>
          <div className="report-detail__body report-ingredients">
            {key.map((item) => <IngredientDetails item={item} key={`key-${item.name}`} />)}
          </div>
        </details>
      )}
      {other.length > 0 && (
        <details className="report-detail">
          <summary><span>Остальные ингредиенты</span><small>{other.length} компонентов</small></summary>
          <div className="report-detail__body report-ingredients">
            {other.map((item) => <IngredientDetails item={item} key={`other-${item.name}`} />)}
          </div>
        </details>
      )}
    </div>
  )
}
