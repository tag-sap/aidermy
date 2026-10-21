// Подготовка фото для Vision: не склеиваем стороны, сохраняем читаемость INCI.
export function fileToResizedDataUrl(file: File, maxDim = 2000): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        try {
          let { width, height } = img
          if (width > maxDim || height > maxDim) {
            const scale = Math.min(maxDim / width, maxDim / height)
            width = Math.round(width * scale)
            height = Math.round(height * scale)
          }
          const canvas = document.createElement("canvas")
          canvas.width = width
          canvas.height = height
          const ctx = canvas.getContext("2d")
          if (!ctx) {
            resolve(reader.result as string)
            return
          }
          ctx.drawImage(img, 0, 0, width, height)
          resolve(canvas.toDataURL("image/jpeg", 0.9))
        } catch {
          resolve(reader.result as string)
        }
      }
      img.onerror = () => resolve(reader.result as string)
      img.src = reader.result as string
    }
    reader.onerror = () => reject(new Error("Не удалось прочитать файл"))
    reader.readAsDataURL(file)
  })
}
