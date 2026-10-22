import { useEffect, useRef, type ReactNode } from "react"

type AnimatedBorderWrapperProps = {
  children: ReactNode
  active: boolean
  className?: string
  borderRadius?: string
  duration?: number
}

/**
 * Reusable Aceternity-style MovingBorder shell.
 *
 * The animated dot is a separate, pointer-events-none layer and never changes
 * the size or structure of the card inside. CSS hides it on md+ screens and
 * when the user prefers reduced motion.
 */
export function AnimatedBorderWrapper({
  children,
  active,
  className = "",
  borderRadius = "18px",
  duration = 3200,
}: AnimatedBorderWrapperProps) {
  const pathRef = useRef<SVGRectElement | null>(null)
  const dotRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (!active || typeof window === "undefined") return
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    if (!window.matchMedia("(max-width: 767px)").matches) return
    let frame = 0
    const started = performance.now()
    const animate = (now: number) => {
      const path = pathRef.current
      const dot = dotRef.current
      if (path && dot) {
        const length = path.getTotalLength()
        if (length > 0) {
          const position = ((now - started) / duration * length) % length
          const point = path.getPointAtLength(position)
          dot.style.transform = `translate(${point.x}px, ${point.y}px) translate(-50%, -50%)`
        }
      }
      frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [active, duration])

  return (
    <div className={`moving-border ${className}`} style={{ borderRadius }}>
      {active && (
        <div className="moving-border__layer" aria-hidden="true">
          <svg className="moving-border__svg" width="100%" height="100%" preserveAspectRatio="none">
            <rect
              ref={pathRef}
              x="0"
              y="0"
              width="100%"
              height="100%"
              rx={borderRadius}
              ry={borderRadius}
              fill="none"
            />
          </svg>
          <span ref={dotRef} className="moving-border__dot" />
        </div>
      )}
      <div className="moving-border__content">{children}</div>
    </div>
  )
}
