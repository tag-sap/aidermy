'use client'

import { useEffect, useRef } from 'react'

export function CyberGrid() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let width = 0
    let height = 0
    let dpr = 1
    const spacing = 46

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    let raf = 0
    const cycle = 20000

    const render = (t: number) => {
      const phase = (t % cycle) / cycle
      const smoothPhase = Math.sin(phase * Math.PI * 2) * 0.5 + 0.5
      const drift = Math.sin(phase * Math.PI * 2) * 4

      // --- БЕЛЫЙ ФОН ---
      ctx.fillStyle = '#FAF9F6'
      ctx.fillRect(0, 0, width, height)

      // --- СЕТКА: чёрная, едва заметная, оранжевый перелив ---
      const shift = smoothPhase * (width + height)
      const grad = ctx.createLinearGradient(
        -width + shift * 0.3,
        0,
        shift * 0.7,
        height,
      )
      grad.addColorStop(0, 'rgba(0,0,0,0.01)')
      grad.addColorStop(0.3, 'rgba(255,79,0,0.015)')
      grad.addColorStop(0.5, 'rgba(255,79,0,0.025)')
      grad.addColorStop(0.7, 'rgba(255,79,0,0.015)')
      grad.addColorStop(1, 'rgba(0,0,0,0.01)')

      ctx.lineWidth = 0.5
      ctx.strokeStyle = grad
      ctx.beginPath()
      for (let x = -spacing; x <= width + spacing; x += spacing) {
        const gx = x + drift
        ctx.moveTo(gx, 0)
        ctx.lineTo(gx, height)
      }
      for (let y = -spacing; y <= height + spacing; y += spacing) {
        const gy = y + drift
        ctx.moveTo(0, gy)
        ctx.lineTo(width, gy)
      }
      ctx.stroke()

      // --- ТОЧКИ: едва заметные ---
      const bandY = smoothPhase * (height + spacing * 2) - spacing
      for (let x = -spacing; x <= width + spacing; x += spacing) {
        for (let y = -spacing; y <= height + spacing; y += spacing) {
          const gx = x + drift
          const gy = y + drift
          const dist = Math.abs(gy - bandY)
          const near = Math.max(0, 1 - dist / 120)
          const alpha = 0.01 + near * 0.05
          const r = 0.4 + near * 0.6
          ctx.beginPath()
          ctx.arc(gx, gy, r, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(255,79,0,${alpha.toFixed(3)})`
          ctx.fill()
        }
      }

      raf = requestAnimationFrame(render)
    }
    raf = requestAnimationFrame(render)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0"
    />
  )
}