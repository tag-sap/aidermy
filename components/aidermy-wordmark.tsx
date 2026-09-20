/**
 * Фирменное слово «AIdermy»: «AI» (Montserrat) + рукописное «dermy» (Sacramento).
 * compact — маленький статичный вариант для шапки; иначе — крупный для hero-баннера.
 */
export function AIdermyWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`ad-logo ${compact ? 'ad-logo--sm ad-logo--static' : ''}`}>
      <span className="ad-ai"><i>A</i><i>I</i></span>
      <span className="ad-dw">
        <span className="ad-dermy">dermy</span>
        <span className="ad-guide"></span>
        <span className="ad-nib"></span>
      </span>
    </div>
  )
}
