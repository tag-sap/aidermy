'use client'

import { useEffect, useRef } from 'react'

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600&family=Sacramento&display=swap');

.ad-hero{
  --ad-bg:#F4EFE6; --ad-ink:#171A18; --ad-moss:#3E574C; --ad-clay:#C0703F; --ad-soft:#68736D;
  --ad-h:360px; --ad-mesh:118px; --ad-push:175px;
  position:relative; height:var(--ad-h); min-height:300px; overflow:hidden; isolation:isolate;
  display:flex; align-items:center; justify-content:center; border-radius:24px;
  background:
    radial-gradient(110% 80% at 14% 0%,  rgba(255,252,246,.95), transparent 58%),
    radial-gradient(90% 70%  at 88% 14%, rgba(227,174,139,.17), transparent 62%),
    radial-gradient(85% 65%  at 50% 108%,rgba(62,87,76,.15),    transparent 66%),
    linear-gradient(178deg, var(--ad-bg), #EBE4D6);
}
.ad-field{position:absolute;inset:0;z-index:1;pointer-events:none}
.ad-grain{
  position:absolute;inset:0;z-index:2;pointer-events:none;opacity:.42;mix-blend-mode:soft-light;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E");
}
.ad-lock{position:relative;z-index:3;padding:0 24px;display:flex;flex-direction:column;align-items:center;user-select:none}
.ad-logo{display:flex;align-items:baseline;white-space:nowrap;line-height:1;cursor:pointer;transition:transform .5s cubic-bezier(.2,.75,.2,1)}
.ad-logo:hover{transform:translateY(-3px)}
.ad-ai{
  font-family:"Montserrat",sans-serif;font-weight:600;font-size:clamp(50px,12vw,108px);
  letter-spacing:-.06em;line-height:.88;color:var(--ad-ink);
  transform:scaleX(.85);transform-origin:right center;position:relative;z-index:1;display:flex;
}
.ad-ai i{font-style:normal;display:inline-block;opacity:0;filter:blur(9px);transform:translateY(12px)}
.ad-play .ad-ai i{animation:adChar .95s cubic-bezier(.2,.75,.2,1) forwards}
.ad-play .ad-ai i:nth-child(1){animation-delay:.22s}
.ad-play .ad-ai i:nth-child(2){animation-delay:.34s}
@keyframes adChar{to{opacity:1;filter:blur(0);transform:none}}
.ad-dw{position:relative;z-index:2;margin-left:clamp(-12px,-1.2vw,-4px);padding-right:.15em}
.ad-dermy{
  display:block;font-family:"Sacramento",cursive;font-weight:400;font-size:clamp(48px,11.5vw,102px);
  letter-spacing:-.02em;line-height:1;color:var(--ad-moss);transform:translateY(.03em);
  clip-path:inset(-.4em 100% -.4em -.25em);
}
.ad-play .ad-dermy{animation:adWrite 1.9s cubic-bezier(.55,.06,.16,1) .95s forwards}
@keyframes adWrite{
  from{clip-path:inset(-.4em 100% -.4em -.25em)}
  to  {clip-path:inset(-.4em -.25em -.4em -.25em)}
}
.ad-nib{
  position:absolute;left:0;top:44%;width:9px;height:9px;margin-left:-4px;border-radius:50%;
  background:var(--ad-clay);opacity:0;
  box-shadow:0 0 18px 5px rgba(192,112,63,.5),0 0 46px 15px rgba(192,112,63,.16);
  --dw:5.2em;
}
.ad-play .ad-nib{animation:adNib 1.9s cubic-bezier(.55,.06,.16,1) .95s forwards}
@keyframes adNib{
  0%  {opacity:0;transform:translateX(0) scale(.4)}
  9%  {opacity:1;transform:translateX(0) scale(1)}
  86% {opacity:1}
  100%{opacity:0;transform:translateX(var(--dw)) scale(.3)}
}
.ad-guide{
  position:absolute;left:-.1em;bottom:.15em;height:1px;width:calc(100% + .2em);
  transform:scaleX(0);transform-origin:left;
  background:linear-gradient(90deg,transparent,rgba(62,87,76,.34) 12%,rgba(62,87,76,.34) 88%,transparent);
}
.ad-play .ad-guide{animation:adGuide 1.9s cubic-bezier(.55,.06,.16,1) .95s forwards}
@keyframes adGuide{0%{transform:scaleX(0);opacity:1}84%{opacity:1}100%{transform:scaleX(1);opacity:0}}
.ad-tag{margin-top:clamp(12px,1.7vw,22px);text-align:center;opacity:0}
.ad-play .ad-tag{animation:adUp .9s cubic-bezier(.2,.75,.2,1) 2.55s forwards}
@keyframes adUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.ad-rule{display:block;height:1px;width:min(240px,52vw);margin:0 auto 11px;background:rgba(62,87,76,.24);transform:scaleX(0);transform-origin:center}
.ad-play .ad-rule{animation:adRule 1s cubic-bezier(.2,.75,.2,1) 2.4s forwards}
@keyframes adRule{to{transform:scaleX(1)}}
.ad-tag p{margin:0;font-family:"Montserrat",sans-serif;font-weight:500;font-size:clamp(9.5px,1vw,12px);letter-spacing:.09em;color:var(--ad-soft)}
.ad-tag em{font-style:normal;color:var(--ad-moss);border-bottom:1px solid rgba(62,87,76,.3)}
@media(max-width:600px){.ad-hero{--ad-mesh:88px;--ad-push:130px}.ad-ai{letter-spacing:-.05em;transform:scaleX(.87)}}
@media(prefers-reduced-motion:reduce){
  .ad-play .ad-ai i,.ad-play .ad-dermy,.ad-play .ad-nib,.ad-play .ad-guide,.ad-play .ad-tag,.ad-play .ad-rule{animation:none!important}
  .ad-ai i{opacity:1;filter:none;transform:none}
  .ad-dermy{clip-path:none}
  .ad-nib,.ad-guide{display:none}
  .ad-tag,.ad-rule{opacity:1;transform:none}
  .ad-rule{transform:scaleX(1)}
}
`

export function AdHero() {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const lock = host.querySelector('.ad-lock') as HTMLElement | null
    if (!lock) return
    // Узкие ненулевые ссылки для вложенных функций (TS не сужает типы в замыканиях).
    const root: HTMLDivElement = host
    const lockRoot: HTMLElement = lock

    const RM = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    function measure() {
      const d = root.querySelector('.ad-dermy') as HTMLElement | null
      const n = root.querySelector('.ad-nib') as HTMLElement | null
      if (d && n) n.style.setProperty('--dw', d.getBoundingClientRect().width + 'px')
    }

    function play() {
      lockRoot.classList.remove('ad-play')
      void lockRoot.offsetWidth
      lockRoot.classList.add('ad-play')
    }

    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        measure()
        requestAnimationFrame(measure)
      })
    }
    const onLoad = () => setTimeout(measure, 80)
    window.addEventListener('load', onLoad)
    const onResize = () => measure()
    window.addEventListener('resize', onResize)

    requestAnimationFrame(play)
    const logo = host.querySelector('.ad-logo')
    logo?.addEventListener('click', () => {
      measure()
      play()
    })

    let cleanupParticles: (() => void) | undefined
    if (!RM) {
      const cv = host.querySelector('.ad-field') as HTMLCanvasElement | null
      if (cv) {
        const ctx = cv.getContext('2d')
        if (ctx) cleanupParticles = initParticles(host, cv, ctx)
      }
    }

    return () => {
      window.removeEventListener('load', onLoad)
      window.removeEventListener('resize', onResize)
      cleanupParticles?.()
    }
  }, [])

  return (
    <>
      <style>{CSS}</style>
      <div className="ad-hero" id="adHero" ref={hostRef}>
        <canvas className="ad-field"></canvas>
        <div className="ad-grain"></div>
        <div className="ad-lock" id="adLock">
          <div className="ad-logo" title="Кликни — перепишется">
            <span className="ad-ai"><i>A</i><i>I</i></span>
            <span className="ad-dw">
              <span className="ad-dermy">dermy</span>
              <span className="ad-guide"></span>
              <span className="ad-nib"></span>
            </span>
          </div>
          <div className="ad-tag">
            <span className="ad-rule"></span>
            <p>Уход, который подходит <em>тебе</em></p>
          </div>
        </div>
      </div>
    </>
  )
}

type P = { x: number; y: number; vx: number; vy: number; bx: number; by: number; r: number; a: number }

function initParticles(host: HTMLElement, cv: HTMLCanvasElement, ctx: CanvasRenderingContext2D) {
  let W = 0
  let H = 0
  let pts: P[] = []
  let raf = 0
  let live = true

  const css = getComputedStyle(host)
  let MESH = parseFloat(css.getPropertyValue('--ad-mesh')) || 118
  let PUSH = parseFloat(css.getPropertyValue('--ad-push')) || 175
  const m = { x: -9e4, y: -9e4 }

  function size() {
    const r = host.getBoundingClientRect()
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    W = r.width
    H = r.height
    cv.width = Math.round(W * dpr)
    cv.height = Math.round(H * dpr)
    cv.style.width = W + 'px'
    cv.style.height = H + 'px'
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    MESH = parseFloat(css.getPropertyValue('--ad-mesh')) || 118
    PUSH = parseFloat(css.getPropertyValue('--ad-push')) || 175
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
    const r = host.getBoundingClientRect()
    m.x = e.clientX - r.left
    m.y = e.clientY - r.top
  }
  const onLeave = () => {
    m.x = -9e4
    m.y = -9e4
  }
  host.addEventListener('pointermove', onMove, { passive: true })
  host.addEventListener('pointerleave', onLeave)

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

  const observer = new IntersectionObserver(
    (en) => {
      const vis = en[0].isIntersecting
      if (vis && !live) {
        live = true
        frame()
      } else if (!vis && live) {
        live = false
        cancelAnimationFrame(raf)
      }
    },
    { threshold: 0 },
  )
  observer.observe(host)

  let rt = 0
  const onResizeDebounced = () => {
    clearTimeout(rt)
    rt = window.setTimeout(() => size(), 160)
  }
  window.addEventListener('resize', onResizeDebounced)

  return () => {
    live = false
    cancelAnimationFrame(raf)
    host.removeEventListener('pointermove', onMove)
    host.removeEventListener('pointerleave', onLeave)
    observer.disconnect()
    window.removeEventListener('resize', onResizeDebounced)
  }
}

