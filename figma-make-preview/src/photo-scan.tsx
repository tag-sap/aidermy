import { useEffect, useRef, useState } from "react"
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

const MAX_IMAGES = 10
const MAX_FILE_BYTES = 12 * 1024 * 1024
const ACCEPTED_IMAGE = "image/jpeg,image/png,image/webp"

function isSupportedImage(file: File): boolean {
  if (/^image\/(jpeg|png|webp)$/i.test(file.type || "")) return true
  // Some mobile browsers expose an empty MIME type for gallery files.
  return /\.(jpe?g|png|webp)$/i.test(file.name || "")
}

function imageLimitMessage(): string {
  return `Можно добавить не больше ${MAX_IMAGES} фото. Удалите лишний кадр, чтобы продолжить.`
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
    // A discovered/imported card is not a completed check. Do not create a
    // placeholder Match: ScoreBadge would treat it as a legacy verdict.
    match: check && score != null
      ? {
          score,
          verdict: check.verdict,
          recommendation_status: check.recommendation_status,
          summary: check.summary,
          safe_ingredients: check.safe_ingredients,
          caution_ingredients: check.caution_ingredients,
          analysis_id: check.analysis_id,
        }
      : undefined,
  }
}

function CameraGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="25" height="25" aria-hidden="true" focusable="false">
      <path d="M4 8.5h3.2l1.4-2h6.8l1.4 2H20v10H4z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <circle cx="12" cy="13.2" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}

function CloseGlyph() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function PhotoTile({ image, index, busy, onView, onRemove, onMakePrimary }: {
  image: string
  index: number
  busy: boolean
  onView: () => void
  onRemove: () => void
  onMakePrimary: () => void
}) {
  return (
    <div className="scan-photo-tile">
      <button type="button" className="scan-photo-tile__view" onClick={onView} disabled={busy} aria-label={`Открыть фото ${index + 1}`}>
        <img src={image} alt={`Фото ${index + 1}`} />
        <span>{index === 0 ? "Лицевая" : `Кадр ${index + 1}`}</span>
      </button>
      <button type="button" className="scan-photo-tile__remove" onClick={onRemove} disabled={busy} aria-label={`Удалить фото ${index + 1}`}><CloseGlyph /></button>
      {index > 0 && (
        <button type="button" className="scan-photo-tile__primary" onClick={onMakePrimary} disabled={busy}>
          Сделать лицевой
        </button>
      )}
    </div>
  )
}

export function PhotoScan({ guestToken, onContinue }: {
  guestToken?: string
  onContinue: (product: Product) => void
}) {
  const [images, setImages] = useState<string[]>([])
  const [viewIndex, setViewIndex] = useState<number | null>(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [cameraBusy, setCameraBusy] = useState(false)
  const [cameraError, setCameraError] = useState("")
  const [status, setStatus] = useState<ScanStatus>("idle")
  const [result, setResult] = useState<ScanResponse | null>(null)
  const [draft, setDraft] = useState<ScanDraftPayload | null>(null)
  const [readyProduct, setReadyProduct] = useState<ScanProductPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState("")
  const galleryRef = useRef<HTMLInputElement | null>(null)
  const filesRef = useRef<HTMLInputElement | null>(null)
  const cameraFallbackRef = useRef<HTMLInputElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const skinType = getUserProfile().skinType || "Нормальная"
  // A front photo alone is enough to identify the product and run web search;
  // a back photo is requested later only if the composition is missing.
  const canScan = images.length >= 1 && !busy
  const isExistingDraft = Boolean(draft?.id)
  const canSave = Boolean(draft?.brand?.trim()) && Boolean(draft?.name?.trim()) && splitIngredients(draft?.ingredients || "").length >= 2 && !saving

  const resetResult = () => {
    setStatus("idle")
    setResult(null)
    setDraft(null)
    setReadyProduct(null)
    setError("")
  }

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setCameraReady(false)
  }

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }, [])

  const closeCamera = () => {
    stopStream()
    setCameraOpen(false)
    setCameraBusy(false)
    setCameraError("")
  }

  const openCamera = async () => {
    setCameraOpen(true)
    setCameraError("")
    setCameraBusy(true)
    setCameraReady(false)
    // Let React mount the video element before attaching the stream.
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Браузер не поддерживает встроенную камеру")
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      })
      streamRef.current = stream
      const video = videoRef.current
      if (!video) throw new Error("Не удалось показать камеру")
      video.srcObject = stream
      await video.play()
      setCameraReady(true)
    } catch (e) {
      stopStream()
      setCameraError(
        errorText(e, "Не удалось открыть камеру. Проверьте разрешение или выберите фото из галереи/файлов."),
      )
    } finally {
      setCameraBusy(false)
    }
  }

  const handleFiles = async (files: FileList | File[] | null) => {
    const selected = Array.from(files || [])
    if (!selected.length) return
    const room = MAX_IMAGES - images.length
    if (room <= 0) {
      setError(imageLimitMessage())
      return
    }
    if (selected.length > room) setError(imageLimitMessage())
    const prepared: string[] = []
    let invalid = ""
    for (const file of selected.slice(0, room)) {
      if (!isSupportedImage(file)) {
        invalid = "Поддерживаются JPEG, PNG и WebP. PDF и другие документы не принимаются как фото."
        continue
      }
      if (file.size > MAX_FILE_BYTES) {
        invalid = "Одно из изображений больше 12 МБ. Выберите файл меньшего размера."
        continue
      }
      try {
        prepared.push(await fileToResizedDataUrl(file, 2400))
      } catch {
        invalid = "Не удалось прочитать одно из изображений. Возможно, файл повреждён."
      }
    }
    if (prepared.length) {
      setImages((current) => [...current, ...prepared].slice(0, MAX_IMAGES))
      resetResult()
      setError("")
    }
    if (invalid) setError(invalid)
  }

  const removeImage = (index: number) => {
    setImages((current) => current.filter((_, i) => i !== index))
    setViewIndex(null)
    resetResult()
  }

  const makePrimary = (index: number) => {
    setImages((current) => {
      if (index <= 0 || index >= current.length) return current
      const next = [...current]
      const [picked] = next.splice(index, 1)
      return [picked, ...next]
    })
    setViewIndex(null)
    resetResult()
  }

  const capturePhoto = () => {
    if (images.length >= MAX_IMAGES) {
      setError(imageLimitMessage())
      return
    }
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError("Камера ещё не готова. Подождите мгновение и повторите.")
      return
    }
    const scale = Math.min(1, 2400 / Math.max(video.videoWidth, video.videoHeight))
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    const context = canvas.getContext("2d")
    if (!context) {
      setError("Не удалось сохранить кадр. Попробуйте загрузить фото из галереи.")
      return
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    setImages((current) => [...current, canvas.toDataURL("image/jpeg", 0.9)].slice(0, MAX_IMAGES))
    resetResult()
    setCameraError("")
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
      const data = await api.scanProduct({ front_image: images[0], back_images: images.slice(1) })
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

  const checkAndContinue = async (item: ScanProductPayload, ingredientsOverride?: string) => {
    setChecking(true)
    setError("")
    try {
      const ingredients = (ingredientsOverride ?? item.ingredients ?? "").trim()
      const profile = buildProfile()
      // New/edited cards must be checked against the exact composition the
      // user sees and confirms, not only against a name lookup in the DB.
      const check = splitIngredients(ingredients).length >= 2
        ? await api.checkWithIngredients({
            product_name: productName(item.brand, item.name),
            brand: item.brand,
            skin_type: skinType,
            profile,
            ingredients,
            image_url: item.image_url || undefined,
            guest_token: guestToken,
          })
        : await api.check({
            product_name: productName(item.brand, item.name),
            skin_type: skinType,
            profile,
            image_url: item.image_url || undefined,
            guest_token: guestToken,
          })
      onContinue(toProduct(item, check, images[0] || "", skinType))
    } catch (e) {
      setError(errorText(e, "Карточка сохранена, но проверить совместимость не удалось."))
    } finally {
      setChecking(false)
    }
  }

  const chooseCandidate = (candidate: ScanCandidatePayload) => {
    if (candidate.has_inci !== false) {
      // Selecting the right card is identification, not a compatibility check.
      // The user starts the check explicitly from the ready screen.
      setReadyProduct(candidate)
      setStatus("ready")
      setError("")
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
      // A card already present in the catalog must not be recreated or have
      // its canonical composition overwritten by the editor.
      if (isExistingDraft) {
        await checkAndContinue(
          {
            id: draft.id ?? undefined,
            slug: draft.slug,
            brand: draft.brand || "",
            name: draft.name || "",
            image_url: draft.image_url,
            ingredients: ingredients.join(", "),
            volume: draft.volume || undefined,
            variant: draft.variant || undefined,
            barcode: draft.barcode || undefined,
            ingredients_source: draft.ingredients_source,
            source_url: draft.source_url,
          },
          ingredients.join(", "),
        )
        return
      }
      // The user reviewed the draft and pressed "save and check", so this is a
      // user-confirmed scan even when the text came from a web page. Marking it
      // as a retailer import would make Evaluation demand a source URL that a
      // newly created card does not have.
      const sourceType = "scan"
      const created = await api.createProduct({
        brand: draft.brand || "",
        name: draft.name || "",
        ingredients,
        slug: draft.slug || "",
        image_data_url: images[0] || "",
        source_url: draft.source_url || undefined,
        volume: draft.volume || undefined,
        variant: draft.variant || undefined,
        barcode: draft.barcode || undefined,
        category: draft.type || undefined,
        source_type: sourceType,
      })
      setReadyProduct(created.product)
      setStatus("ready")
      await checkAndContinue(
        {
          ...created.product,
          brand: draft.brand || created.product.brand,
          name: draft.name || created.product.name,
          ingredients: ingredients.join(", "),
          volume: draft.volume || created.product.volume,
        },
        ingredients.join(", "),
      )
    } catch (e) {
      setError(errorText(e, "Не удалось сохранить карточку продукта."))
    } finally {
      setSaving(false)
    }
  }


  return (
    <div className="scan-form">
      <div className="scan-photo-actions">
        <button type="button" className="btn btn--primary btn--small" onClick={() => void openCamera()} disabled={busy || saving || checking || images.length >= MAX_IMAGES}>
          Снять на камеру
        </button>
        <button type="button" className="btn btn--secondary btn--small" onClick={() => galleryRef.current?.click()} disabled={busy || saving || checking || images.length >= MAX_IMAGES}>
          Выбрать из галереи
        </button>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => filesRef.current?.click()} disabled={busy || saving || checking || images.length >= MAX_IMAGES}>
          Выбрать файлы
        </button>
      </div>
      <p className="panel__note">
        Достаточно лицевой стороны. Заднюю сторону с составом добавьте, если продукт не найдётся автоматически — это необязательно. Кадры можно добавлять по одному и в любом порядке.
      </p>
      {images.length > 0 ? (
        <div className="scan-photo-list">
          {images.map((image, index) => (
            <PhotoTile
              key={`photo-${index}-${image.slice(-24)}`}
              image={image}
              index={index}
              busy={busy || saving || checking}
              onView={() => setViewIndex(index)}
              onRemove={() => removeImage(index)}
              onMakePrimary={() => makePrimary(index)}
            />
          ))}
        </div>
      ) : (
        <div className="scan-photo-empty">
          <strong>Пока нет фотографий</strong>
          <small>Можно снять на камеру, выбрать из галереи или открыть файлы. PDF не поддерживается.</small>
        </div>
      )}
      <div className="scan-photo-add">
        <span className={`scan-photo-count ${images.length >= MAX_IMAGES ? "is-limit" : ""}`}>
          Выбрано: <strong>{images.length}</strong> / {MAX_IMAGES}
        </span>
        {images.length === 1 && <small>Можно распознать по одной лицевой стороне. Если состав не найдётся, добавьте заднюю сторону или введите INCI вручную.</small>}
        {images.length >= MAX_IMAGES && <small>Достигнут лимит. Удалите лишний кадр, чтобы добавить новый.</small>}
      </div>
      <input ref={galleryRef} type="file" accept="image/*" multiple hidden onChange={(e) => { void handleFiles(e.target.files); e.target.value = "" }} />
      <input ref={filesRef} type="file" accept={ACCEPTED_IMAGE} multiple hidden onChange={(e) => { void handleFiles(e.target.files); e.target.value = "" }} />
      <input ref={cameraFallbackRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { void handleFiles(e.target.files); closeCamera(); e.target.value = "" }} />

      <button type="button" className="btn btn--primary" onClick={() => void scan()} disabled={!canScan}>
        {busy ? "Распознаём упаковку и состав…" : "Распознать продукт"}
      </button>
      {error && status !== "error" && <p className="scan-error" role="alert">{error}</p>}

      {cameraOpen && (
        <div className="camera-backdrop" role="presentation">
          <section className="camera-modal" role="dialog" aria-modal="true" aria-label="Съёмка упаковки">
            <header className="camera-modal__head">
              <div><strong>Съёмка упаковки</strong><small>{images.length} из {MAX_IMAGES} кадров</small></div>
              <button type="button" className="camera-modal__close" onClick={closeCamera} aria-label="Закрыть камеру"><CloseGlyph /></button>
            </header>
            {cameraError ? (
              <div className="camera-fallback">
                <p>{cameraError}</p>
                <div className="camera-fallback__actions">
                  <button type="button" className="btn btn--secondary btn--small" onClick={() => { closeCamera(); galleryRef.current?.click() }}>Из галереи</button>
                  <button type="button" className="btn btn--ghost btn--small" onClick={() => { closeCamera(); filesRef.current?.click() }}>Выбрать файлы</button>
                  <button type="button" className="btn btn--ghost btn--small" onClick={() => cameraFallbackRef.current?.click()}>Системная камера</button>
                </div>
              </div>
            ) : (
              <div className="camera-stage">
                <video ref={videoRef} playsInline muted autoPlay aria-label="Изображение с камеры" />
                <span className="camera-stage__hint">{cameraBusy ? "Открываем камеру…" : cameraReady ? "Совместите упаковку и нажмите на кнопку съёмки" : "Ожидаем камеру…"}</span>
              </div>
            )}
            {images.length > 0 && (
              <div className="camera-shots">
                {images.map((image, index) => (
                  <span className="camera-shot" key={`${index}-${image.slice(-20)}`}>
                    <img src={image} alt={`Кадр ${index + 1}`} />
                    <button type="button" onClick={() => removeImage(index)} aria-label={`Удалить кадр ${index + 1}`}><CloseGlyph /></button>
                  </span>
                ))}
              </div>
            )}
            <footer className="camera-modal__foot">
              <button type="button" className="camera-shutter" onClick={capturePhoto} disabled={!cameraReady || cameraBusy || images.length >= MAX_IMAGES} aria-label="Сделать снимок" title="Сделать снимок"><CameraGlyph /></button>
              <button type="button" className="btn btn--secondary btn--small camera-modal__done" onClick={closeCamera}>Готово · {images.length}</button>
            </footer>
          </section>
        </div>
      )}

      {viewIndex != null && images[viewIndex] && (
        <div className="scan-viewer-backdrop" onClick={() => setViewIndex(null)} role="presentation">
          <div className="scan-viewer" onClick={(event) => event.stopPropagation()}>
            <img src={images[viewIndex]} alt={`Фото ${viewIndex + 1}`} />
            <div className="scan-viewer__actions">
              <button type="button" className="btn btn--ghost btn--small" onClick={() => setViewIndex(null)}>Закрыть</button>
              <button type="button" className="btn btn--secondary btn--small" onClick={() => removeImage(viewIndex)}>Удалить кадр</button>
              <button type="button" className="btn btn--primary btn--small" onClick={() => makePrimary(viewIndex)} disabled={viewIndex === 0}>Сделать лицевой</button>
            </div>
          </div>
        </div>
      )}

      {status === "ready" && readyProduct && (
        <div className="panel scan-ready">
          <p className="eyebrow">Продукт определён</p>
          <div className="scan-ready__row">
            <img src={readyProduct.image_url || images[0]} alt="" />
            <div>
              <h3>{readyProduct.name}</h3>
              <p>{[readyProduct.brand, readyProduct.category].filter(Boolean).join(" · ")}</p>
              {readyProduct.variant && <p className="panel__note">Вариант: {readyProduct.variant}</p>}
              {readyProduct.barcode && <p className="panel__note">Штрихкод: {readyProduct.barcode}</p>}
              <p className="panel__note">{sourceLabel(readyProduct.ingredients_source)}</p>
              {readyProduct.ingredients_source === "local" && (
                <p className="panel__note">Состав загружен из каталога Aidermy и не редактируется.</p>
              )}
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
          {!isExistingDraft && (
            <p className="scan-hint">*Заполните пустые поля бренда и названия — эти данные нужны для проверки.</p>
          )}
          <div className="scan-form__row">
            <label><span>Бренд *</span><input value={draft.brand || ""} placeholder="*заполните в этом поле" onChange={(e) => setDraft({ ...draft, brand: e.target.value })} /></label>
            <label><span>Объём</span><input value={draft.volume || ""} onChange={(e) => setDraft({ ...draft, volume: e.target.value })} /></label>
          </div>
          <label className="scan-form__area"><span>Название *</span><input value={draft.name || ""} placeholder="*заполните в этом поле" onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
          <label className="scan-form__area">
            <span>Состав (INCI) {isExistingDraft ? "· из каталога" : ""}</span>
            <textarea
              rows={5}
              value={draft.ingredients}
              readOnly={isExistingDraft}
              disabled={isExistingDraft}
              onChange={(e) => setDraft({ ...draft, ingredients: e.target.value })}
            />
          </label>
          {isExistingDraft && <p className="panel__note">Состав найденной карточки Aidermy защищён от редактирования.</p>}
          {draft.barcode && <p className="panel__note">Штрихкод: {draft.barcode}</p>}
          {draft.variant && <p className="panel__note">Вариант: {draft.variant}</p>}
          <p className="panel__note">Карточка не сохраняется, пока вы её не подтвердите. Состав с фото не считается проверенным.</p>
          {!canSave && <p className="scan-warning">Для сохранения нужны бренд, название и как минимум два ингредиента.</p>}
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
          <p className="panel__note">
            Можно сфотографировать заднюю сторону с составом или вернуться в «Выбрать способ» и открыть «Ручной ввод» либо «Вставить ссылку».
          </p>
          <div className="scan-ready__actions">
            <button type="button" className="btn btn--primary" onClick={resetResult}>Повторить</button>
            <button type="button" className="btn btn--ghost" onClick={() => { setStatus("idle"); setResult(null) }}>Заменить фото</button>
          </div>
        </div>
      )}
    </div>
  )
}

