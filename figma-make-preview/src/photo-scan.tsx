import { useRef, useState } from "react"
import { api, ApiError, type CheckResult, type ScanCandidatePayload, type ScanDraftPayload, type ScanProductPayload } from "./api"
import type { Product } from "./data"
import { buildProfile, getUserProfile } from "./mapping"
import { fileToResizedDataUrl } from "./image-utils"

type ScanStatus = "idle" | "scanning" | "ready" | "ambiguous" | "needs_confirmation" | "not_found" | "error"

type ScanResponse = {
  status: "ready" | "ambiguous" | "needs_confirmation" | "not_found"
  message?: string
  product?: ScanProductPayload
  candidates?: ScanCandidatePayload[]
  draft?: ScanDraftPayload | null
  can_analyze?: boolean
  warnings?: string[]
  identified?: {
    brand?: string
    product_name?: string
    variant?: string | null
    type?: string | null
    volume?: string | null
    barcode?: string | null
    missing_fields?: string[]
  }
}

const MISSING_LABELS: Record<string, string> = {
  brand: "бренд",
  product_name: "название",
  variant: "вариант",
  type: "тип",
  volume: "объём",
  barcode: "штрихкод",
}

function productName(brand?: string, name?: string): string {
  const b = (brand || "").trim()
  const n = (name || "").trim()
  if (b && n && !n.toLowerCase().startsWith(b.toLowerCase())) return `${b}\n${n}`
  return n || b
}

function splitIngredients(value: string): string[] {
  return value
    .replace(/;/g, ",")
    .split(/[,\n]+/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function sourceLabel(source?: string): string {
  if (source === "scraped") return "Состав получен с найденной страницы товара"
  if (source === "back_photo") return "Состав распознан с задней фотографии — требует проверки"
  if (source === "local") return "Состав из каталога Aidermy"
  return "Состав не получен"
}

function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return fallback
}

function toProduct(
  item: ScanProductPayload,
  check: CheckResult | null,
  frontImage: string,
  skinType: string,
): Product {
  const score = check && typeof check.score === "number" ? check.score : null
  return {
    id: item.id ?? Date.now(),
    brand: item.brand || "",
    name: item.name || "Продукт",
    cabinet: "face",
    category: item.category || "Специальный уход",
    image: item.image_url || frontImage,
    tags: item.category ? [item.category] : [],
    state: "want",
    slug: item.slug,
    ingredients: item.ingredients,
    barcode: item.barcode,
    variant: item.variant,
    match: check
      ? {
          score,
          verdict: check.verdict,
          recommendation_status: check.recommendation_status,
          summary: check.summary,
          safe_ingredients: check.safe_ingredients,
          caution_ingredients: check.caution_ingredients,
          analysis_id: check.analysis_id,
        }
      : { score: null },
  }
}

function PhotoSlot({ label, hint, image, busy, onPick, onRemove }: {
  label: string
  hint: string
  image: string
  busy: boolean
  onPick: () => void
  onRemove: () => void
}) {
  return (
    <div className={`scan-photo-slot ${image ? "scan-photo-slot--filled" : ""}`}>
      <button type="button" className="scan-photo-slot__pick" onClick={onPick} disabled={busy}>
        {image ? <img src={image} alt={label} /> : (
          <>
            <span className="scan-photo-slot__icon">+</span>
            <strong>{label}</strong>
            <small>{hint}</small>
          </>
        )}
      </button>
      {image && (
        <>
          <span className="scan-photo-slot__label">{label}</span>
          <button type="button" className="scan-photo-slot__remove" onClick={onRemove} disabled={busy} aria-label={`Удалить: ${label}`}>
            ×
          </button>
        </>
      )}
    </div>
  )
}

export function PhotoScan({ guestToken, onContinue }: {
  guestToken?: string
  onContinue: (product: Product) => void
}) {
  const [front, setFront] = useState("")
  const [backs, setBacks] = useState<string[]>([])
  const [backEditIndex, setBackEditIndex] = useState<number | null>(null)
  const [status, setStatus] = useState<ScanStatus>("idle")
  const [result, setResult] = useState<ScanResponse | null>(null)
  const [draft, setDraft] = useState<ScanDraftPayload | null>(null)
  const [readyProduct, setReadyProduct] = useState<ScanProductPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState("")
  const frontRef = useRef<HTMLInputElement | null>(null)
  const backRef = useRef<HTMLInputElement | null>(null)

  const skinType = getUserProfile().skinType || "Нормальная"
  const canScan = Boolean(front && backs.length > 0) && !busy
  const MAX_BACK_PHOTOS = 6
  const canSave = Boolean(draft?.name?.trim()) && splitIngredients(draft?.ingredients || "").length >= 2 && !saving

  const resetResult = () => {
    setStatus("idle")
    setResult(null)
    setDraft(null)
    setReadyProduct(null)
    setError("")
  }

  const handleFrontFile = async (file: File | undefined) => {
    if (!file) return
    if (!/^image\/(jpeg|png|webp)$/i.test(file.type)) {
      setError("Поддерживаются JPEG, PNG или WebP.")
      return
    }
    if (file.size > 12 * 1024 * 1024) {
      setError("Файл больше 12 МБ. Сделайте фото меньшего размера.")
      return
    }
    try {
      setFront(await fileToResizedDataUrl(file, 2000))
      resetResult()
    } catch (e) {
      setError(errorText(e, "Не удалось прочитать фото."))
    }
  }

  const handleBackFile = async (file: File | undefined) => {
    if (!file) return
    if (!/^image\/(jpeg|png|webp)$/i.test(file.type)) {
      setError("Поддерживаются JPEG, PNG или WebP.")
      return
    }
    if (file.size > 12 * 1024 * 1024) {
      setError("Файл больше 12 МБ. Сделайте фото меньшего размера.")
      return
    }
    try {
      const dataUrl = await fileToResizedDataUrl(file, 2400)
      setBacks((current) => {
        if (backEditIndex == null) {
          if (current.length >= MAX_BACK_PHOTOS) return current
          return [...current, dataUrl]
        }
        return current.map((item, index) => (index === backEditIndex ? dataUrl : item))
      })
      setBackEditIndex(null)
      resetResult()
    } catch (e) {
      setError(errorText(e, "Не удалось прочитать фото."))
    }
  }

  const openBackPicker = (index: number | null) => {
    setBackEditIndex(index)
    backRef.current?.click()
  }

  const scan = async () => {
    if (!canScan) return
    setBusy(true)
    setError("")
    setResult(null)
    setDraft(null)
    setReadyProduct(null)
    setStatus("scanning")
    try {
      const data = await api.scanProduct({ front_image: front, back_images: backs })
      setResult(data as ScanResponse)
      if (data.status === "ready" && data.product) {
        setReadyProduct(data.product)
        setStatus("ready")
      } else if (data.status === "ambiguous") {
        setStatus("ambiguous")
      } else if (data.status === "needs_confirmation") {
        setDraft(data.draft || null)
        setStatus("needs_confirmation")
      } else {
        setStatus("not_found")
        setError(data.message || "Не удалось распознать продукт.")
      }
    } catch (e) {
      setStatus("error")
      setError(errorText(e, "Не удалось выполнить сканирование."))
    } finally {
      setBusy(false)
    }
  }

  const checkAndContinue = async (item: ScanProductPayload) => {
    setChecking(true)
    setError("")
    try {
      const check = await api.check({
        product_name: productName(item.brand, item.name),
        skin_type: skinType,
        profile: buildProfile(),
        guest_token: guestToken,
      })
      onContinue(toProduct(item, check, front, skinType))
    } catch (e) {
      setError(errorText(e, "Карточка сохранена, но проверить совместимость не удалось."))
    } finally {
      setChecking(false)
    }
  }

  const chooseCandidate = (candidate: ScanCandidatePayload) => {
    if (candidate.has_inci !== false) {
      void checkAndContinue(candidate)
      return
    }
    setDraft((current) => ({
      ...(result?.draft || current || { ingredients: "", ingredients_source: "none" }),
      id: candidate.id,
      slug: candidate.slug,
      brand: candidate.brand || current?.brand || "",
      name: candidate.name || current?.name || "",
      image_url: candidate.image_url || current?.image_url || "",
      barcode: candidate.barcode || current?.barcode || "",
      variant: candidate.variant || current?.variant || "",
    }))
    setStatus("needs_confirmation")
    setError("")
  }

  const saveAndCheck = async () => {
    if (!draft || !canSave) return
    setSaving(true)
    setError("")
    try {
      const ingredients = splitIngredients(draft.ingredients)
      const sourceType = draft.ingredients_source === "scraped" ? "retailer" : "scan"
      const created = await api.createProduct({
        brand: draft.brand || "",
        name: draft.name || "",
        ingredients,
        slug: draft.slug || "",
        image_data_url: front,
        source_url: draft.source_url || undefined,
        volume: draft.volume || undefined,
        variant: draft.variant || undefined,
        barcode: draft.barcode || undefined,
        category: draft.type || undefined,
        source_type: sourceType,
      })
      setReadyProduct(created.product)
      setStatus("ready")
      await checkAndContinue(created.product)
    } catch (e) {
      setError(errorText(e, "Не удалось сохранить карточку продукта."))
    } finally {
      setSaving(false)
    }
  }


  return (
    <div className="scan-form">
      <div className="scan-photo-grid">
        <PhotoSlot
          label="Фото 1 — лицевая"
          hint="Бренд, название, объём"
          image={front}
          busy={busy || saving || checking}
          onPick={() => frontRef.current?.click()}
          onRemove={() => { setFront(""); resetResult() }}
        />
        <PhotoSlot
          label="Фото 2 — задняя"
          hint="Состав INCI, штрихкод"
          image={backs[0] || ""}
          busy={busy || saving || checking}
          onPick={() => openBackPicker(backs.length ? 0 : null)}
          onRemove={() => { setBacks((current) => current.slice(1)); resetResult() }}
        />
        {backs.slice(1).map((image, index) => (
          <PhotoSlot
            key={`back-${index + 1}`}
            label={`Доп. фото состава ${index + 1}`}
            hint="Продолжение списка INCI"
            image={image}
            busy={busy || saving || checking}
            onPick={() => openBackPicker(index + 1)}
            onRemove={() => { setBacks((current) => current.filter((_, i) => i !== index + 1)); resetResult() }}
          />
        ))}
      </div>
      <div className="scan-photo-add">
        <button type="button" className="btn btn--ghost btn--small" onClick={() => openBackPicker(null)} disabled={backs.length >= MAX_BACK_PHOTOS || busy}>
          + Добавить ещё фото состава
        </button>
        <small>Можно до {MAX_BACK_PHOTOS} фото задней стороны. Это помогает, если состав не помещается на круглой банке или флаконе.</small>
      </div>
      <p className="panel__note">
        Сфотографируйте лицевую сторону и состав на упаковке. Если весь состав не помещается в один кадр, добавьте несколько снимков задней стороны — так мы точнее прочитаем ингредиенты.
      </p>
      <input ref={frontRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden onChange={(e) => { void handleFrontFile(e.target.files?.[0]); e.target.value = "" }} />
      <input ref={backRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden onChange={(e) => { void handleBackFile(e.target.files?.[0]); e.target.value = "" }} />

      <button type="button" className="btn btn--primary" onClick={() => void scan()} disabled={!canScan}>
        {busy ? "Распознаём упаковку и состав…" : "Распознать продукт"}
      </button>
      {(!front || backs.length === 0) && !busy && <p className="panel__note">Загрузите лицевую сторону и хотя бы одно фото состава — без них распознавание не запускается.</p>}
      {error && status !== "error" && <p className="scan-error" role="alert">{error}</p>}

      {status === "ready" && readyProduct && (
        <div className="panel scan-ready">
          <p className="eyebrow">Продукт определён</p>
          <div className="scan-ready__row">
            <img src={readyProduct.image_url || front} alt="" />
            <div>
              <h3>{readyProduct.name}</h3>
              <p>{[readyProduct.brand, readyProduct.category].filter(Boolean).join(" · ")}</p>
              {readyProduct.variant && <p className="panel__note">Вариант: {readyProduct.variant}</p>}
              {readyProduct.barcode && <p className="panel__note">Штрихкод: {readyProduct.barcode}</p>}
              <p className="panel__note">{sourceLabel(readyProduct.ingredients_source)}</p>
            </div>
          </div>
          <div className="scan-ready__actions">
            <button type="button" className="btn btn--primary" onClick={() => void checkAndContinue(readyProduct)} disabled={checking}>
              {checking ? "Проверяем…" : "Проверить"}
            </button>
            <button type="button" className="btn btn--ghost" onClick={resetResult} disabled={checking}>Это не тот продукт</button>
          </div>
        </div>
      )}

      {status === "ambiguous" && result && (
        <div className="scan-candidates">
          <p className="panel__note">{result.message || "Выберите подходящую карточку."}</p>
          {(result.candidates || []).map((candidate) => (
            <div className="scan-candidate" key={`${candidate.slug}-${candidate.id}`}>
              {candidate.image_url ? <img src={candidate.image_url} alt="" /> : <span className="scan-candidate__icon">?</span>}
              <div>
                <strong>{[candidate.brand, candidate.name].filter(Boolean).join(" · ")}</strong>
                <small>
                  Совпадение: {Math.round((candidate.match_score || 0) * 100)}%
                  {candidate.has_inci === false ? " · состав нужно проверить" : ""}
                </small>
              </div>
              <button type="button" className="btn btn--ghost btn--small" onClick={() => chooseCandidate(candidate)}>Это он</button>
            </div>
          ))}
          <button type="button" className="guest-link" onClick={() => { setStatus("idle"); setResult(null) }}>Ни один не подходит — повторить</button>
        </div>
      )}


      {status === "needs_confirmation" && draft && (
        <div className="panel scan-draft">
          <p className="eyebrow">Проверьте карточку</p>
          <p className="panel__note">{sourceLabel(draft.ingredients_source)}</p>
          {(result?.warnings || []).map((warning) => <p className="scan-warning" key={warning}>{warning}</p>)}
          {(result?.identified?.missing_fields || []).length > 0 && (
            <p className="panel__note">
              Не удалось определить: {(result?.identified?.missing_fields || []).map((field) => MISSING_LABELS[field] || field).join(", ")}.
            </p>
          )}
          {draft.source_url && <a className="guest-link" href={draft.source_url} target="_blank" rel="noreferrer">Источник карточки</a>}
          <div className="scan-form__row">
            <label><span>Бренд</span><input value={draft.brand || ""} onChange={(e) => setDraft({ ...draft, brand: e.target.value })} /></label>
            <label><span>Объём</span><input value={draft.volume || ""} onChange={(e) => setDraft({ ...draft, volume: e.target.value })} /></label>
          </div>
          <label className="scan-form__area"><span>Название *</span><input value={draft.name || ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
          <label className="scan-form__area"><span>Состав (INCI)</span><textarea rows={5} value={draft.ingredients} onChange={(e) => setDraft({ ...draft, ingredients: e.target.value })} /></label>
          {draft.barcode && <p className="panel__note">Штрихкод: {draft.barcode}</p>}
          {draft.variant && <p className="panel__note">Вариант: {draft.variant}</p>}
          <p className="panel__note">Карточка не сохраняется, пока вы её не подтвердите. Состав с фото не считается проверенным.</p>
          {!canSave && <p className="scan-warning">Для сохранения нужны название и как минимум два ингредиента.</p>}
          {error && <p className="scan-error" role="alert">{error}</p>}
          <button type="button" className="btn btn--primary" onClick={() => void saveAndCheck()} disabled={!canSave}>
            {saving ? "Сохраняем…" : "Сохранить карточку и проверить"}
          </button>
          <button type="button" className="guest-link" onClick={resetResult}>Сфотографировать заново</button>
        </div>
      )}

      {(status === "error" || status === "not_found") && (
        <div className="scan-empty">
          <p className="scan-error" role="alert">{error || result?.message || "Не удалось распознать продукт."}</p>
          <div className="scan-ready__actions">
            <button type="button" className="btn btn--primary" onClick={resetResult}>Повторить</button>
            <button type="button" className="btn btn--ghost" onClick={() => { setStatus("idle"); setResult(null) }}>Заменить фото</button>
          </div>
        </div>
      )}
    </div>
  )
}

