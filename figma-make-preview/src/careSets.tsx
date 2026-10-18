import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  api,
  careSetsApi,
  type CareSetSummary,
  type CareSetDetail,
  type CareSetTemplate,
  type CareSetTemplateDetail,
  type CareSetCandidate,
  type CareSetCompatibility,
} from "./api"

function Icon({ name, size = 20 }: { name: "plus" | "back" | "close" | "chevron" | "sparkle" | "trash" | "box" | "check"; size?: number }) {
  const paths: Record<string, ReactNode> = {
    plus: (<path d="M12 5v14M5 12h14" />),
    back: (<path d="M19 12H5M11 6l-6 6 6 6" />),
    close: (<path d="M18 6 6 18M6 6l12 12" />),
    chevron: (<path d="m9 6 6 6-6 6" />),
    sparkle: (<path d="M12 3l1.7 4.6L18 9l-4.3 1.4L12 15l-1.7-4.6L6 9l4.3-1.4L12 3zM19 14l.9 2.4L22 17l-2.1.6L19 20l-.9-2.4L16 17l2.1-.6L19 14z" />),
    trash: (<><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /><path d="M10 11v6M14 11v6" /></>),
    box: (<><path d="M21 8 12 3 3 8v8l9 5 9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></>),
    check: (<path d="m5 12 4 4L19 6" />),
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function ScorePill({ score }: { score: number | null }) {
  if (score == null) return <span className="care-pill care-pill--na">нет данных</span>
  const tone = score < 40 ? "bad" : score < 60 ? "warn" : "good"
  return <span className={`care-pill care-pill--${tone}`}>{score}%</span>
}

type View = "list" | "detail" | "autopick"

export function CareSetsPage({ user, onAuth }: { user: { name: string } | null; onAuth: () => void }) {
  const [view, setView] = useState<View>("list")
  const [sets, setSets] = useState<CareSetSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState("")

  const [currentId, setCurrentId] = useState<number | null>(null)
  const [detail, setDetail] = useState<CareSetDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [templates, setTemplates] = useState<CareSetTemplate[]>([])
  const [tplDetail, setTplDetail] = useState<CareSetTemplateDetail | null>(null)
  const [stepIndex, setStepIndex] = useState(0)
  const [candidates, setCandidates] = useState<CareSetCandidate[]>([])
  const [candLoading, setCandLoading] = useState(false)
  const [chosen, setChosen] = useState<Record<number, CareSetCandidate | null>>({})

  const [searchQ, setSearchQ] = useState("")
  const [searchResults, setSearchResults] = useState<{ id: number; slug: string; name: string; brand: string; image_url: string }[]>([])
  const [searching, setSearching] = useState(false)

  useEffect(() => { if (!toast) return; const t = window.setTimeout(() => setToast(""), 2200); return () => window.clearTimeout(t) }, [toast])

  const loadSets = async () => {
    setLoading(true)
    try {
      const r = await careSetsApi.list()
      setSets(r.sets || [])
    } catch (e) {
      if (e instanceof Error && /401|token|авториз/i.test(e.message)) onAuth()
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (view === "list") loadSets() }, [view])

  const openSet = async (id: number) => {
    setCurrentId(id)
    setDetailLoading(true)
    setDetail(null)
    try {
      setDetail(await careSetsApi.detail(id))
      setView("detail")
    } catch {
      setToast("Не удалось открыть сборку")
    } finally {
      setDetailLoading(false)
    }
  }

  const createSet = async () => {
    const name = window.prompt("Название сборки", "Мой уход")
    if (name == null) return
    const trimmed = name.trim()
    if (!trimmed) return
    try {
      const r = await careSetsApi.create(trimmed, "manual")
      setToast("Сборка создана")
      await loadSets()
      await openSet(r.id)
    } catch {
      setToast("Не удалось создать сборку")
    }
  }

  const renameSet = async (id: number, current: string) => {
    const name = window.prompt("Новое название", current)
    if (name == null) return
    const trimmed = name.trim()
    if (!trimmed) return
    try {
      await careSetsApi.rename(id, trimmed)
      setToast("Название обновлено")
      await loadSets()
      if (currentId === id) setDetail((d) => (d ? { ...d, name: trimmed } : d))
    } catch {
      setToast("Не удалось переименовать")
    }
  }

  const deleteSet = async (id: number) => {
    if (!window.confirm("Удалить сборку?")) return
    try {
      await careSetsApi.remove(id)
      setToast("Сборка удалена")
      setView("list")
      setCurrentId(null)
      setDetail(null)
      await loadSets()
    } catch {
      setToast("Не удалось удалить сборку")
    }
  }

  const refreshDetail = async () => {
    if (currentId == null) return
    try {
      setDetail(await careSetsApi.detail(currentId))
    } catch {
      /* ignore */
    }
  }

  const addItem = async (slug: string) => {
    if (currentId == null) return
    try {
      const r = await careSetsApi.addItem(currentId, slug)
      setToast(r.duplicate ? "Продукт уже в сборке" : "Добавлено")
      setSearchQ("")
      setSearchResults([])
      await refreshDetail()
    } catch {
      setToast("Не удалось добавить продукт")
    }
  }

  const removeItem = async (itemId: number) => {
    if (currentId == null) return
    try {
      await careSetsApi.removeItem(currentId, itemId)
      await refreshDetail()
    } catch {
      setToast("Не удалось удалить продукт")
    }
  }

  useEffect(() => {
    const q = searchQ.trim()
    if (!q) { setSearchResults([]); return }
    setSearching(true)
    const t = window.setTimeout(async () => {
      try {
        const res = await api.catalog({ search: q, limit: 8 })
        const mapped = (res.products || []).map((p: any) => ({
          id: p.id, slug: p.slug, name: p.name, brand: p.brand, image_url: p.image_url,
        }))
        setSearchResults(mapped)
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => window.clearTimeout(t)
  }, [searchQ])

  const startAutopick = async () => {
    try {
      const r = await careSetsApi.templates()
      setTemplates(r.templates || [])
      setTplDetail(null)
      setStepIndex(0)
      setChosen({})
      setCandidates([])
      setView("autopick")
    } catch {
      setToast("Не удалось загрузить сценарии")
    }
  }

  const pickTemplate = async (slug: string) => {
    try {
      setTplDetail(await careSetsApi.template(slug))
      setStepIndex(0)
      setChosen({})
      setCandidates([])
    } catch {
      setToast("Не удалось загрузить сценарий")
    }
  }

  const loadCandidates = async (idx: number, chosenSlugs: string[]) => {
    if (!tplDetail) return
    const step = tplDetail.steps[idx]
    if (!step) return
    setCandLoading(true)
    setCandidates([])
    try {
      const r = await careSetsApi.candidates(tplDetail.slug, idx, chosenSlugs)
      setCandidates(r.candidates || [])
    } catch {
      setCandidates([])
    } finally {
      setCandLoading(false)
    }
  }

  useEffect(() => {
    if (view === "autopick" && tplDetail) {
      const slugs = Object.values(chosen).filter(Boolean).map((c: any) => c.slug)
      loadCandidates(stepIndex, slugs)
    }
  }, [view, tplDetail, stepIndex])

  const selectCandidate = (c: CareSetCandidate) => {
    setChosen((prev) => ({ ...prev, [stepIndex]: c }))
    if (tplDetail && stepIndex < tplDetail.steps.length - 1) {
      setStepIndex(stepIndex + 1)
    }
  }

  const skipStep = () => {
    setChosen((prev) => ({ ...prev, [stepIndex]: null }))
    if (tplDetail && stepIndex < tplDetail.steps.length - 1) {
      setStepIndex(stepIndex + 1)
    }
  }

  const chosenList = useMemo(() => {
    if (!tplDetail) return []
    return tplDetail.steps
      .map((s, i) => ({ step: s, candidate: chosen[i] ?? null }))
      .filter((x) => x.candidate != null)
  }, [tplDetail, chosen])

  const saveAutopick = async () => {
    if (!tplDetail) return
    const items = chosenList.map((x) => ({ slug: x.candidate!.slug }))
    try {
      const r = await careSetsApi.create(tplDetail.title, "autopick", items)
      setToast("Сборка сохранена")
      setView("list")
      setTplDetail(null)
      setChosen({})
      await loadSets()
      await openSet(r.id)
    } catch {
      setToast("Не удалось сохранить сборку")
    }
  }

  return (
    <div className="page">
      {view === "list" && (
        <>
          <div className="page-head">
            <div>
              <p className="eyebrow">Уход</p>
              <h1>Сборки</h1>
              <p className="care-lead">Ваши персональные списки косметики. Создайте вручную или соберите автоматически по сценарию.</p>
            </div>
            <div className="page-head__actions">
              <button type="button" className="btn btn--ghost" onClick={startAutopick}><Icon name="sparkle" size={17} /> Автоподбор</button>
              <button type="button" className="btn btn--primary" onClick={createSet}><Icon name="plus" size={17} /> Создать сборку</button>
            </div>
          </div>

          {loading ? (
            <p className="empty">Загружаем…</p>
          ) : sets.length === 0 ? (
            <p className="empty">Сборок пока нет. Создайте первую или соберите автоматически.</p>
          ) : (
            <div className="care-list">
              {sets.map((s) => (
                <div key={s.id} className="care-card">
                  <button type="button" className="care-card__main" onClick={() => openSet(s.id)}>
                    <span className="care-card__icon"><Icon name="box" size={20} /></span>
                    <span className="care-card__meta">
                      <strong>{s.name || "Без названия"}</strong>
                      <small>{s.item_count} шт. · {s.source === "autopick" ? "автоподбор" : "вручную"}</small>
                    </span>
                    <Icon name="chevron" size={18} />
                  </button>
                  <div className="care-card__actions">
                    <button type="button" className="care-textbtn" onClick={() => renameSet(s.id, s.name)}>Переименовать</button>
                    <button type="button" className="care-textbtn care-textbtn--danger" onClick={() => deleteSet(s.id)}>Удалить</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {view === "detail" && detail && (
        <>
          <button type="button" className="care-back" onClick={() => { setView("list"); setDetail(null); setCurrentId(null) }}><Icon name="back" size={15} /> Назад</button>
          <div className="page-head">
            <div>
              <p className="eyebrow">{detail.source === "autopick" ? "Автоподбор" : "Сборка"}</p>
              <h1>{detail.name || "Без названия"}</h1>
            </div>
            <div className="page-head__actions">
              <button type="button" className="btn btn--ghost" onClick={() => renameSet(detail.id, detail.name)}>Переименовать</button>
              <button type="button" className="btn btn--ghost" onClick={() => deleteSet(detail.id)}>Удалить</button>
            </div>
          </div>

          <div className="care-compat">
            <CompatCard title="Совместимость с профилем" compat={detail.profile_compatibility} />
            <CompatCard title="Совместимость между собой" compat={detail.products_compatibility} />
          </div>

          <div className="care-section">
            <h3>Продукты</h3>
            {detail.items.length === 0 ? (
              <p className="empty">Сборка пуста. Добавьте продукты ниже.</p>
            ) : (
              <div className="care-items">
                {detail.items.map((it) => (
                  <div key={it.item_id} className="care-item">
                    <img src={it.image_url} alt="" loading="lazy" />
                    <span className="care-item__meta">
                      <strong>{it.name}</strong>
                      <small>{it.brand}{it.category ? ` · ${it.category}` : ""}</small>
                    </span>
                    <ScorePill score={it.score} />
                    <button type="button" className="icon-btn" onClick={() => removeItem(it.item_id)} aria-label="Удалить"><Icon name="trash" size={16} /></button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="care-section">
            <h3>Добавить продукт</h3>
            <div className="search">
              <input value={searchQ} onChange={(e) => setSearchQ(e.target.value)} placeholder="Название, бренд или актив…" />
            </div>
            {searching && <p className="care-hint">Ищем…</p>}
            {searchResults.length > 0 && (
              <div className="care-search-results">
                {searchResults.map((p) => (
                  <div key={p.id} className="care-item">
                    <img src={p.image_url} alt="" loading="lazy" />
                    <span className="care-item__meta"><strong>{p.name}</strong><small>{p.brand}</small></span>
                    <button type="button" className="btn btn--small" onClick={() => addItem(p.slug)}><Icon name="plus" size={14} /> Добавить</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {view === "autopick" && (
        <>
          <button type="button" className="care-back" onClick={() => { setView("list"); setTplDetail(null) }}><Icon name="back" size={15} /> Назад</button>
          {!tplDetail ? (
            <>
              <div className="page-head">
                <div><p className="eyebrow">Автоподбор</p><h1>Выберите сценарий</h1></div>
              </div>
              {templates.length === 0 ? (
                <p className="empty">Сценарии недоступны.</p>
              ) : (
                <div className="care-tpl-grid">
                  {templates.map((t) => (
                    <button type="button" key={t.slug} className="care-tpl" onClick={() => pickTemplate(t.slug)}>
                      <strong>{t.title}</strong>
                      <small>{t.description}</small>
                      <span className="care-tpl__go"><Icon name="chevron" size={16} /></span>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="page-head">
                <div><p className="eyebrow">Автоподбор</p><h1>{tplDetail.title}</h1></div>
              </div>
              {stepIndex < tplDetail.steps.length ? (
                <div className="care-step">
                  <div className="care-step__head">
                    <span className="care-step__count">Шаг {stepIndex + 1} из {tplDetail.steps.length}</span>
                    <strong>{tplDetail.steps[stepIndex].category}</strong>
                    {tplDetail.steps[stepIndex].is_optional && <span className="chip">можно пропустить</span>}
                  </div>
                  {candLoading ? (
                    <p className="empty">Подбираем…</p>
                  ) : candidates.length === 0 ? (
                    <p className="empty">Кандидатов не нашлось{chosen[stepIndex] != null ? "" : ". Можно пропустить этап."}</p>
                  ) : (
                    <div className="care-cand-grid">
                      {candidates.map((c) => (
                        <button type="button" key={c.slug} className="care-cand" onClick={() => selectCandidate(c)}>
                          <img src={c.image_url} alt="" loading="lazy" />
                          <span className="care-cand__meta">
                            <strong>{c.name}</strong>
                            <small>{c.brand}</small>
                          </span>
                          <ScorePill score={c.score} />
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="care-step__actions">
                    {tplDetail.steps[stepIndex].is_optional && (
                      <button type="button" className="btn btn--ghost" onClick={skipStep}>Пропустить</button>
                    )}
                    {stepIndex > 0 && (
                      <button type="button" className="btn btn--ghost" onClick={() => setStepIndex(stepIndex - 1)}>Назад</button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="care-summary">
                  <h2>Готово</h2>
                  <p className="care-lead">Выбрано продуктов: {chosenList.length}. Сохраните как обычную сборку — её можно редактировать.</p>
                  {chosenList.length === 0 ? (
                    <p className="empty">Ничего не выбрано.</p>
                  ) : (
                    <div className="care-items">
                      {chosenList.map((x) => (
                        <div key={x.step.position} className="care-item">
                          <img src={x.candidate!.image_url} alt="" loading="lazy" />
                          <span className="care-item__meta">
                            <strong>{x.candidate!.name}</strong>
                            <small>{x.step.category}</small>
                          </span>
                          <ScorePill score={x.candidate!.score} />
                        </div>
                      ))}
                    </div>
                  )}
                  <button type="button" className="btn btn--primary" onClick={saveAutopick} disabled={chosenList.length === 0}>Сохранить сборку</button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

function CompatCard({ title, compat }: { title: string; compat: CareSetCompatibility }) {
  return (
    <div className="care-compat__card">
      <div className="care-compat__head">
        <strong>{title}</strong>
        <ScorePill score={compat.score} />
      </div>
      {compat.coverage && (
        <p className="care-compat__sub">Проверено {compat.coverage.scored} из {compat.coverage.total}</p>
      )}
      {compat.note && <p className="care-compat__note">{compat.note}</p>}
      {compat.conflicts && compat.conflicts.length > 0 && (
        <div className="care-conflicts">
          {compat.conflicts.map((c, i) => (
            <div key={i} className="care-conflict">
              <strong>{c.label}</strong>
              <small>{(c.products || []).join(" + ")}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
