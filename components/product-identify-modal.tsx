'use client'

import { useRef, useState } from 'react'
import { X, Camera, LoaderCircle, Keyboard } from 'lucide-react'

// Каскад: фото продукта -> Vision -> БД -> автоматический Web Search -> fallback.
type Stage = 'idle' | 'identifying' | 'searching' | 'found' | 'fallback' | 'error'
type Identified = { brand: string; name: string; variant: string | null; type: string | null; confidence: number }
type Product = { slug: string; name: string; brand: string; ingredients: string }

function fileToResizedDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        try {
          const maxDim = 1600
          let { width, height } = img
          if (width > maxDim || height > maxDim) {
            const scale = Math.min(maxDim / width, maxDim / height)
            width = Math.round(width * scale)
            height = Math.round(height * scale)
          }
          const canvas = document.createElement('canvas')
          canvas.width = width
          canvas.height = height
          const ctx = canvas.getContext('2d')
          if (!ctx) { resolve(reader.result as string); return }
          ctx.drawImage(img, 0, 0, width, height)
          resolve(canvas.toDataURL('image/jpeg', 0.85))
        } catch { resolve(reader.result as string) }
      }
      img.onerror = () => resolve(reader.result as string)
      img.src = reader.result as string
    }
    reader.onerror = () => reject(new Error('Не удалось прочитать файл'))
    reader.readAsDataURL(file)
  })
}

export function ProductIdentifyModal({
  onClose,
  onProduct,
  onPhotoComposition,
  onManual,
}: {
  onClose: () => void
  onProduct: (name: string, brand: string) => void
  onPhotoComposition: (prefill: { brand?: string; name?: string }) => void
  onManual: (prefill: { brand?: string; name?: string }) => void
}) {
  const [stage, setStage] = useState<Stage>('idle')
  const [status, setStatus] = useState('')
  const [identified, setIdentified] = useState<Identified | null>(null)
  const [product, setProduct] = useState<Product | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const busy = stage === 'identifying' || stage === 'searching'

  const run = async (images: string[]) => {
    setStage('identifying')
    setStatus('Определяем продукт…')
    try {
      const res = await fetch('/api/product/identify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ images }),
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setIdentified(data.identified)

      if (data.product && data.has_inci) {
        setProduct(data.product)
        setStage('found')
        return
      }

      setStage('searching')
      setStatus('Ищем продукт в интернете…')
      const ws = await fetch('/api/product/web-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand: data.identified?.brand || '', name: data.identified?.name || '' }),
      })
      if (ws.ok) {
        const wsData = await ws.json()
        if (wsData.found && wsData.product) {
          setProduct(wsData.product)
          setStage('found')
          return
        }
      }
      setStage('fallback')
    } catch {
      setStage('error')
      setStatus('Не удалось определить продукт. Попробуйте ещё раз или введите вручную.')
    }
  }

  const onFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const imgs: string[] = []
    for (const f of Array.from(files)) imgs.push(await fileToResizedDataUrl(f))
    if (imgs.length) await run(imgs)
  }

  return (
    <div className="fixed inset-0 z-[90] flex flex-col bg-background">
      <div className="flex items-center justify-between border-b border-gray-200/60 px-4 py-3">
        <h2 className="font-advaken text-lg text-foreground">найти продукт</h2>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="size-5" /></button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-6">
        {stage === 'idle' && (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <Camera className="size-12 text-muted-foreground/30" />
            <h3 className="text-2xl font-medium text-foreground">Сфотографируйте продукт</h3>
            <p className="max-w-xs text-sm text-muted-foreground">Мы определим бренд и название, найдём состав и проверим совместимость.</p>
            <button onClick={() => fileRef.current?.click()} className="w-full max-w-sm rounded-2xl bg-primary py-4 text-base font-medium text-primary-foreground transition-colors hover:bg-primary/90">
              СФОТОГРАФИРОВАТЬ ПРОДУКТ
            </button>
            <input ref={fileRef} type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={(e) => onFiles(e.target.files)} />
          </div>
        )}

        {busy && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <LoaderCircle className="size-10 animate-spin text-primary" />
            <p className="text-lg font-medium text-foreground">{status}</p>
            <p className="text-xs text-muted-foreground">Это займёт несколько секунд</p>
          </div>
        )}

        {stage === 'found' && product && (
          <div className="flex flex-col gap-5">
            <div className="rounded-2xl border border-gray-200/60 p-4">
              <p className="text-xs text-muted-foreground">Найден продукт</p>
              {product.brand && <p className="mt-1 font-advaken text-xl text-foreground">{product.brand}</p>}
              <p className="text-base text-foreground/80">{product.name}</p>
            </div>
            <button onClick={() => onProduct(product.name, product.brand)} className="w-full rounded-2xl bg-primary py-4 text-base font-medium text-primary-foreground transition-colors hover:bg-primary/90">
              ПРОВЕРИТЬ СОВМЕСТИМОСТЬ
            </button>
            <button onClick={() => setStage('fallback')} className="w-full text-sm text-muted-foreground/70">
              Это не тот продукт
            </button>
          </div>
        )}

        {stage === 'fallback' && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <h3 className="text-2xl font-medium text-foreground">Не удалось найти состав</h3>
            {identified?.brand && <p className="text-sm text-muted-foreground">Определено: {identified.brand} {identified.name}</p>}
            <p className="max-w-xs text-sm text-muted-foreground">Сфотографируйте состав на упаковке или введите его вручную.</p>
            <button onClick={() => onPhotoComposition({ brand: identified?.brand || '', name: identified?.name || '' })} className="flex w-full max-w-sm items-center justify-center gap-2 rounded-2xl bg-primary py-4 text-base font-medium text-primary-foreground transition-colors hover:bg-primary/90">
              <Camera className="size-5" /> СФОТОГРАФИРОВАТЬ СОСТАВ
            </button>
            <button onClick={() => onManual({ brand: identified?.brand || '', name: identified?.name || '' })} className="flex w-full max-w-sm items-center justify-center gap-2 rounded-2xl border border-gray-300 py-4 text-base font-medium text-foreground transition-colors hover:bg-gray-50">
              <Keyboard className="size-5" /> ВВЕСТИ ВРУЧНУЮ
            </button>
          </div>
        )}

        {stage === 'error' && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <p className="text-lg font-medium text-foreground">{status}</p>
            <div className="flex w-full max-w-sm flex-col gap-3">
              <button onClick={() => setStage('idle')} className="rounded-2xl bg-primary py-4 text-base font-medium text-primary-foreground">
                ПОВТОРИТЬ ФОТО
              </button>
              <button onClick={() => onManual({ brand: identified?.brand || '', name: identified?.name || '' })} className="rounded-2xl border border-gray-300 py-4 text-base font-medium text-foreground">
        
                ВВЕСТИ ВРУЧНУЮ
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
