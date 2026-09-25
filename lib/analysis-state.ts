// lib/analysis-state.ts
//
// Единая модель состояния продукта для всего UI.
// Разделяет три сущности:
//   - Static Product Model   (объективная модель продукта) — НЕ даёт score;
//   - User Analysis          (персональный анализ из истории проверок) — ЕДИНСТВЕННЫЙ источник score;
//   - AI Report              (человеческая рецензия по запросу «Показать отчёт») — НЕ даёт score.
//
// Логика состояний описана в ТЗ:
//   NOT_ANALYZED      — score скрыт, «Анализ ещё не выполнен», [Проверить совместимость];
//   ANALYSIS_PENDING  — «Анализируем…», кнопка повторного запуска отключена;
//   ANALYSIS_FAILED   — «Анализ не выполнен», [Повторить анализ];
//   ANALYZED          — score виден, [Показать отчёт].

export type ProductAnalysis = {
  verdict?: string
  summary?: string
  score?: number | null
  safe_ingredients?: string[]
  caution_ingredients?: string[]
  active_ingredients?: {
    name: string
    position: number
    concentration: string
    effectiveness?: string
  } | null
  how_to_use?: { application: string; time: string; note: string } | null
  expectations?: { when: string; normal: string; danger: string } | null
  report?: string | null
}

export type AnalysisState =
  | { kind: 'NOT_ANALYZED' }
  | { kind: 'ANALYSIS_PENDING' }
  | { kind: 'ANALYSIS_FAILED'; error: string }
  | { kind: 'ANALYZED'; score: number; analysis: ProductAnalysis }

/**
 * Выводит единое состояние из данных бэкенда.
 * Score считается валидным ТОЛЬКО при наличии актуального User Analysis (analysis).
 */
export function deriveAnalysisState(args: {
  analysis: ProductAnalysis | null | undefined
  score: number | null | undefined
  loading: boolean
  error: string
}): AnalysisState {
  if (args.loading) return { kind: 'ANALYSIS_PENDING' }
  if (args.error) return { kind: 'ANALYSIS_FAILED', error: args.error }

  const hasAnalysis = args.analysis != null
  const score = typeof args.score === 'number' ? args.score : args.analysis?.score ?? null
  if (hasAnalysis && score != null) {
    return { kind: 'ANALYZED', score, analysis: args.analysis as ProductAnalysis }
  }
  return { kind: 'NOT_ANALYZED' }
}

export const ANALYSIS_LABELS = {
  NOT_ANALYZED: 'Анализ ещё не выполнен',
  PENDING: 'Анализируем…',
  FAILED: 'Анализ не выполнен',
} as const

export const ANALYSIS_ACTIONS = {
  CHECK: 'Проверить совместимость',
  SHOW_REPORT: 'Показать отчёт',
  RETRY: 'Повторить анализ',
  VIEW_REPORT: 'Посмотреть отчёт',
} as const
