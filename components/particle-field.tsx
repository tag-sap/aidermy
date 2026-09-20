'use client'

import { useEffect, useRef } from 'react'

type P = { x: number; y: number; vx: number; vy: number; bx: number; by: number; r: number; a: number }

/**
 * Глобальный фон: сетка частиц, которые разлетаются от курсора и «хватают» указатель.
 */
export function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    return initField(cv, ctx)
  }, [])

  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none fixed inset-0 z-0" />
}

function initField(cv: HTMLCanvasElement, ctx: CanvasRenderingContext2D) {
  let W = 0
  let H = 0
  let pts: P[] = []
  let raf = 0
  let live = true

  const MESH = 118
  const PUSH = 175
  const m = { x: -9e4, y: -9e4 }

  function size() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    W = window.innerWidth
    H = window.innerHeight
    cv.width = Math.round(W * dpr)
    cv.height = Math.round(H * dpr)
    cv.style.width = W + 'px'
    cv.style.height = H + 'px'
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    build()
  }

  function build() {
    const n = Math.round(Math.max(24, Math.min(92, (W * H) / 15000)))
    pts = []
    for (let i = 0; i < n; i++) {
      const bx = (Math.random() - 0.5) * 0.2
      const by = (Math.random() - 0.5) * 0.2
      pts.push({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: bx,
        vy: by,
        bx,
        by,
        r: Math.random() * 1.6 + 0.7,
        a: Math.random() * 0.45 + 0.3,
      })
    }
  }

  const onMove = (e: PointerEvent) => {
    m.x = e.clientX
    m.y = e.clientY
  }
  const onLeave = () => {
    m.x = -9e4
    m.y = -9e4
  }
  window.addEventListener('pointermove', onMove, { passive: true })
  window.addEventListener('pointerleave', onLeave)

  function frame() {
    ctx.clearRect(0, 0, W, H)

    for (let i = 0; i < pts.length; i++) {
      const p = pts[i]
      const dx = p.x - m.x
      const dy = p.y - m.y
      const d2 = dx * dx + dy * dy
      if (d2 < PUSH * PUSH) {
        const d = Math.sqrt(d2) || 1
        const f = 1 - d / PUSH
        p.vx += (dx / d) * f * f * 1.5
        p.vy += (dy / d) * f * f * 1.5
      }
      p.vx += (p.bx - p.vx) * 0.028
      p.vy += (p.by - p.vy) * 0.028
      p.x += p.vx
      p.y += p.vy

      if (p.x < -30) p.x = W + 30
      else if (p.x > W + 30) p.x = -30
      if (p.y < -30) p.y = H + 30
      else if (p.y > H + 30) p.y = -30
    }

    ctx.lineWidth = 0.65
    for (let a = 0; a < pts.length; a++) {
      for (let b = a + 1; b < pts.length; b++) {
        const A = pts[a]
        const B = pts[b]
        const ex = A.x - B.x
        const ey = A.y - B.y
        const dd = ex * ex + ey * ey
        if (dd < MESH * MESH) {
          const dist = Math.sqrt(dd)
          const k = 1 - dist / MESH
          ctx.strokeStyle = 'rgba(62,87,76,' + (k * 0.13).toFixed(3) + ')'
          ctx.beginPath()
          ctx.moveTo(A.x, A.y)
          ctx.lineTo(B.x, B.y)
          ctx.stroke()
        }
      }
    }

    for (let c = 0; c < pts.length; c++) {
      const q = pts[c]
      const qx = q.x - m.x
      const qy = q.y - m.y
      const qd = Math.sqrt(qx * qx + qy * qy)
      if (qd < PUSH * 0.9) {
        ctx.strokeStyle = 'rgba(192,112,63,' + ((1 - qd / (PUSH * 0.9)) * 0.22).toFixed(3) + ')'
        ctx.beginPath()
        ctx.moveTo(m.x, m.y)
        ctx.lineTo(q.x, q.y)
        ctx.stroke()
      }
    }

    for (let e = 0; e < pts.length; e++) {
      const t = pts[e]
      const near = Math.max(0, 1 - Math.hypot(t.x - m.x, t.y - m.y) / 210)
      ctx.fillStyle =
        'rgba(' +
        (124 + (near * 68) | 0) + ',' +
        (151 - (near * 39) | 0) + ',' +
        (138 - (near * 60) | 0) + ',' +
        (t.a * 0.38 + near * 0.5).toFixed(3) + ')'
      ctx.beginPath()
      ctx.arc(t.x, t.y, t.r + near * 1.5, 0, 6.283)
      ctx.fill()
    }

    if (live) raf = requestAnimationFrame(frame)
  }

  size()
  frame()

  let rt = 0
  const onResize = () => {
    clearTimeout(rt)
    rt = window.setTimeout(() => size(), 160)
  }
  window.addEventListener('resize', onResize)

  const onVis = () => {
    if (document.hidden) {
      live = false
      cancelAnimationFrame(raf)
    } else if (!live) {
      live = true
      frame()
    }
  }
  document.addEventListener('visibilitychange', onVis)

  return () => {
    live = false
    cancelAnimationFrame(raf)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerleave', onLeave)
    window.removeEventListener('resize', onResize)
    document.removeEventListener('visibilitychange', onVis)
  }
}
