/**
 * Минимальный self-contained GIF-декодер (GIF87a / GIF89a).
 *
 * Нужен для того, чтобы контролировать кадры анимации навигационных вкладок:
 * проигрывать GIF вперёд/назад, останавливаться на последнем кадре и не
 * зацикливать его (обычный <img src="*.gif"> так не умеет).
 *
 * Работает только в браузере (использует ImageData).
 */

export interface GifFrame {
  imageData: ImageData
  delayMs: number
}

export interface GifBBox {
  left: number
  top: number
  width: number
  height: number
}

export interface DecodedGif {
  width: number
  height: number
  frames: GifFrame[]
  /** Объединённый bounding-box непрозрачных пикселей всех кадров. */
  bbox: GifBBox
}

function lzwDecode(minCodeSize: number, data: number[]): number[] {
  const clear = 1 << minCodeSize
  const eoi = clear + 1
  let nextCode = eoi + 1
  let codeSize = minCodeSize + 1
  const table = new Map<number, number[]>()
  const reset = () => {
    table.clear()
    for (let i = 0; i < clear; i++) table.set(i, [i])
    nextCode = eoi + 1
    codeSize = minCodeSize + 1
  }
  reset()

  let prev: number[] | null = null
  const output: number[] = []
  let bitBuffer = 0
  let bitCount = 0
  let pos = 0

  while (pos < data.length) {
    while (bitCount < codeSize && pos < data.length) {
      bitBuffer |= data[pos++] << bitCount
      bitCount += 8
    }
    if (bitCount < codeSize) break

    const code = bitBuffer & ((1 << codeSize) - 1)
    bitBuffer >>>= codeSize
    bitCount -= codeSize

    if (code === clear) {
      reset()
      prev = null
      continue
    }
    if (code === eoi) break

    let entry: number[]
    const existing = table.get(code)
    if (existing !== undefined) {
      entry = existing
    } else if (code === nextCode && prev !== null) {
      entry = [...prev, prev[0]]
    } else {
      // Некорректный код — прерываем, чтобы не зациклиться.
      break
    }

    for (let i = 0; i < entry.length; i++) output.push(entry[i])

    if (prev !== null) {
      table.set(nextCode, [...prev, entry[0]])
      nextCode++
      if (nextCode === 1 << codeSize && codeSize < 12) codeSize++
    }
    prev = entry
  }

  return output
}

function buildFrame(
  indices: number[],
  colorTable: Uint8Array | null,
  transparent: number,
  fullWidth: number,
  fullHeight: number,
  left: number,
  top: number,
  iw: number,
  ih: number
): ImageData {
  const data = new Uint8ClampedArray(fullWidth * fullHeight * 4)
  for (let y = 0; y < ih; y++) {
    for (let x = 0; x < iw; x++) {
      const idx = indices[y * iw + x]
      const px = (top + y) * fullWidth + (left + x)
      const off = px * 4
      if (idx === transparent || !colorTable) {
        data[off + 3] = 0
        continue
      }
      const c = idx * 3
      if (c + 2 >= colorTable.length) {
        data[off + 3] = 0
        continue
      }
      data[off] = colorTable[c]
      data[off + 1] = colorTable[c + 1]
      data[off + 2] = colorTable[c + 2]
      data[off + 3] = 255
    }
  }
  return new ImageData(data, fullWidth, fullHeight)
}

export function decodeGifFromBuffer(buffer: ArrayBuffer): DecodedGif {
  const bytes = new Uint8Array(buffer)
  const dv = new DataView(buffer)

  const header = String.fromCharCode(
    bytes[0],
    bytes[1],
    bytes[2],
    bytes[3],
    bytes[4],
    bytes[5]
  )
  if (header !== 'GIF87a' && header !== 'GIF89a') {
    throw new Error('Not a GIF file')
  }

  const width = dv.getUint16(6, true)
  const height = dv.getUint16(8, true)

  const packed = bytes[10]
  const hasGCT = (packed & 0x80) !== 0
  const gctSize = 1 << ((packed & 0x07) + 1)

  let pos = 13
  let gct: Uint8Array | null = null
  if (hasGCT) {
    gct = bytes.subarray(pos, pos + gctSize * 3)
    pos += gctSize * 3
  }

  const frames: GifFrame[] = []
  let delayMs = 100
  let transparent = -1

  while (pos < bytes.length) {
    const block = bytes[pos++]
    if (block === 0x3b) break // trailer

    if (block === 0x21) {
      const label = bytes[pos++]
      if (label === 0xf9) {
        // Graphic Control Extension
        const size = bytes[pos++]
        const gcePacked = bytes[pos]
        const delay = dv.getUint16(pos + 1, true)
        transparent = gcePacked & 0x01 ? bytes[pos + 3] : -1
        delayMs = Math.max(delay, 1) * 10
        pos += size + 1 // данные + терминатор блока
      } else {
        // Application / Comment / Plain-text extension — пропускаем подблоки.
        while (true) {
          const size = bytes[pos++]
          if (size === 0) break
          pos += size
        }
      }
      continue
    }

    if (block === 0x2c) {
      // Image Descriptor
      const left = dv.getUint16(pos, true)
      const top = dv.getUint16(pos + 2, true)
      const iw = dv.getUint16(pos + 4, true)
      const ih = dv.getUint16(pos + 6, true)
      const ipacked = bytes[pos + 8]
      pos += 9

      let lct: Uint8Array | null = null
      if (ipacked & 0x80) {
        const lctSize = 1 << ((ipacked & 0x07) + 1)
        lct = bytes.subarray(pos, pos + lctSize * 3)
        pos += lctSize * 3
      }

      const minCodeSize = bytes[pos++]

      const lzw: number[] = []
      while (true) {
        const size = bytes[pos++]
        if (size === 0) break
        for (let i = 0; i < size; i++) lzw.push(bytes[pos++])
      }

      const indices = lzwDecode(minCodeSize, lzw)
      const colorTable = lct || gct
      const imageData = buildFrame(
        indices,
        colorTable,
        transparent,
        width,
        height,
        left,
        top,
        iw,
        ih
      )
      frames.push({ imageData, delayMs })
      continue
    }

    // Неизвестный блок — прерываем безопасно.
    throw new Error(`Unknown GIF block 0x${block.toString(16)}`)
  }

  if (frames.length === 0) {
    throw new Error('GIF has no frames')
  }

  // Объединённый bounding-box всех непрозрачных пикселей.
  let minX = width
  let minY = height
  let maxX = -1
  let maxY = -1
  for (const frame of frames) {
    const d = frame.imageData.data
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (d[(y * width + x) * 4 + 3] > 0) {
          if (x < minX) minX = x
          if (x > maxX) maxX = x
          if (y < minY) minY = y
          if (y > maxY) maxY = y
        }
      }
    }
  }

  const bbox: GifBBox =
    maxX >= minX && maxY >= minY
      ? { left: minX, top: minY, width: maxX - minX + 1, height: maxY - minY + 1 }
      : { left: 0, top: 0, width, height }

  return { width, height, frames, bbox }
}

export async function decodeGif(src: string): Promise<DecodedGif> {
  const res = await fetch(src)
  if (!res.ok) throw new Error(`Failed to load GIF: ${res.status}`)
  const buffer = await res.arrayBuffer()
  return decodeGifFromBuffer(buffer)
}


