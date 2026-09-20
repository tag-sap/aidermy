'use client'

import { useEffect, useRef } from 'react'
import { AIdermyWordmark } from './aidermy-wordmark'

/**
 * Hero-баннер лендинга: фирменный логотип AIdermy + подпись.
 * Фон-сетка частиц теперь глобальный (см. ParticleField).
 */
export function AdHero() {
  const lockRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const lock = lockRef.current
    if (!lock) return
    const root = lock.parentElement as HTMLElement | null
    if (!root) return
    // Ненулевые ссылки для вложенных функций (TS не сужает типы в замыканиях).
    const lockEl: HTMLDivElement = lock
    const rootEl: HTMLElement = root

    function measure() {
      const d = rootEl.querySelector('.ad-dermy') as HTMLElement | null
      const n = rootEl.querySelector('.ad-nib') as HTMLElement | null
      if (d && n) n.style.setProperty('--dw', d.getBoundingClientRect().width + 'px')
    }

    function play() {
      lockEl.classList.remove('ad-play')
      void lockEl.offsetWidth
      lockEl.classList.add('ad-play')
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
    const logo = root.querySelector('.ad-logo')
    logo?.addEventListener('click', () => {
      measure()
      play()
    })

    return () => {
      window.removeEventListener('load', onLoad)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  return (
    <div className="ad-hero" id="adHero">
      <div className="ad-lock" id="adLock" ref={lockRef}>
        <AIdermyWordmark />
        <div className="ad-tag">
          <span className="ad-rule"></span>
          <p>Уход, который подходит <em>тебе</em></p>
        </div>
      </div>
    </div>
  )
}
