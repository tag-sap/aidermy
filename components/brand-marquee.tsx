'use client'

import { useEffect, useRef } from 'react'

export function BrandMarquee() {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const rows = containerRef.current?.querySelectorAll('.marquee-row')
    rows?.forEach(row => {
      row.innerHTML = row.innerHTML + row.innerHTML
    })
  }, [])

  return (
    <div
      ref={containerRef}
      className="brand-bg fixed inset-0 z-[-1] pointer-events-none overflow-hidden"
      style={{
        display: 'flex',
        flexDirection: 'column',
        flexWrap: 'nowrap',
        gap: '2px 0',
        padding: '10px 0',
        height: '120vh',
        top: '-10%',
	zIndex: -1,
      }}
    >
      {/* РЯД 1 */}
      <div className="marquee-row marquee-left-fast" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-orbitron" style={{ fontSize: '5.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>CHANEL</span>
        <span className="font-major" style={{ fontSize: '7rem', opacity: 0.4, letterSpacing: '6px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>DIOR</span>
        <span className="font-space" style={{ fontSize: '4.2rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>GUERLAIN</span>
        <span className="font-anton" style={{ fontSize: '6.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>CLARINS</span>
        <span className="font-oswald" style={{ fontSize: '5rem', opacity: 0.4, letterSpacing: '6px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>LANCÔME</span>
      </div>

      {/* РЯД 2 */}
      <div className="marquee-row marquee-right-slow" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-bebas" style={{ fontSize: '4.8rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>ESTÉE LAUDER</span>
        <span className="font-mono" style={{ fontSize: '3.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>LA MER</span>
        <span className="font-bebas" style={{ fontSize: '8rem', opacity: 0.4, letterSpacing: '10px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SISLEY</span>
        <span className="font-space" style={{ fontSize: '4.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>HELENA RUBINSTEIN</span>
      </div>

      {/* РЯД 3 */}
      <div className="marquee-row marquee-left-medium" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-orbitron" style={{ fontSize: '6.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>LANEIGE</span>
        <span className="font-mono" style={{ fontSize: '3.2rem', opacity: 0.4, letterSpacing: '5px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>INNISFREE</span>
        <span className="font-anton" style={{ fontSize: '5.2rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SULWHASOO</span>
        <span className="font-bebas" style={{ fontSize: '7.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>ETUDE HOUSE</span>
        <span className="font-space" style={{ fontSize: '4.2rem', opacity: 0.4, letterSpacing: '8px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>MISSHA</span>
        <span className="font-oswald" style={{ fontSize: '3.8rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SKIN FOOD</span>
      </div>

      {/* РЯД 4 */}
      <div className="marquee-row marquee-right-fast" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-major" style={{ fontSize: '6.5rem', opacity: 0.4, letterSpacing: '6px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>L'OCCITANE</span>
        <span className="font-oswald" style={{ fontSize: '3.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>CAUDALIE</span>
        <span className="font-anton" style={{ fontSize: '5.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>NUXE</span>
        <span className="font-space" style={{ fontSize: '4.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>BIODERMA</span>
        <span className="font-orbitron" style={{ fontSize: '5.5rem', opacity: 0.4, letterSpacing: '4px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>VICHY</span>
        <span className="font-bebas" style={{ fontSize: '4rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>LA ROCHE POSAY</span>
      </div>

      {/* РЯД 5 */}
      <div className="marquee-row marquee-left-slow" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-mono" style={{ fontSize: '6rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>AVÈNE</span>
        <span className="font-space" style={{ fontSize: '3.8rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>URIAGE</span>
        <span className="font-orbitron" style={{ fontSize: '5rem', opacity: 0.4, letterSpacing: '10px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SVR</span>
        <span className="font-bebas" style={{ fontSize: '7rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>FILORGA</span>
        <span className="font-major" style={{ fontSize: '4rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>MAC</span>
        <span className="font-orbitron" style={{ fontSize: '6rem', opacity: 0.4, letterSpacing: '5px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>NARS</span>
      </div>

      {/* РЯД 6 */}
      <div className="marquee-row marquee-right-medium" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-anton" style={{ fontSize: '4.2rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>BOBBI BROWN</span>
        <span className="font-oswald" style={{ fontSize: '5.2rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>MAKE UP FOR EVER</span>
        <span className="font-bebas" style={{ fontSize: '3.2rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>CHARLOTTE TILBURY</span>
        <span className="font-major" style={{ fontSize: '7rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>PAT MCGRATH</span>
        <span className="font-anton" style={{ fontSize: '4.8rem', opacity: 0.4, letterSpacing: '6px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>HUDA BEAUTY</span>
        <span className="font-bebas" style={{ fontSize: '5.8rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>FENTY BEAUTY</span>
      </div>

      {/* РЯД 7 */}
      <div className="marquee-row marquee-left-fast" style={{ display: 'flex', flexWrap: 'nowrap', gap: '0 30px', width: 'max-content', padding: '0 10px' }}>
        <span className="font-orbitron" style={{ fontSize: '8.5rem', opacity: 0.4, letterSpacing: '14px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SHISEIDO</span>
        <span className="font-major" style={{ fontSize: '4.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SK-II</span>
        <span className="font-anton" style={{ fontSize: '6.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>KOSÉ</span>
        <span className="font-space" style={{ fontSize: '3.5rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>KANEBO</span>
        <span className="font-orbitron" style={{ fontSize: '5.5rem', opacity: 0.4, letterSpacing: '8px', display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>SENSAI</span>
        <span className="font-oswald" style={{ fontSize: '4.2rem', opacity: 0.4, display: 'inline-block', whiteSpace: 'nowrap', textTransform: 'uppercase', color: '#111', flexShrink: 0 }}>DECORTÉ</span>
      </div>
    </div>
  )
}
