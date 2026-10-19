import { EXECUTOR_CONTACT, LEGAL_DOCS, LEGAL_PATHS } from "./legal-content"

export function legalDocFromPath(pathname: string): string | null {
  const clean = (pathname || "/").replace(/\/+$/, "").toLowerCase()
  const slug = clean.replace(/^\//, "")
  return slug && LEGAL_DOCS[slug] ? slug : null
}

export function SiteFooter({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <span className="site-footer__brand">айдерми</span>
        <nav className="site-footer__links" aria-label="Юридические документы">
          {Object.entries(LEGAL_PATHS).map(([slug, title]) => (
            <button key={slug} type="button" onClick={() => onNavigate(`/${slug}`)}>
              {title}
            </button>
          ))}
        </nav>
        <a className="site-footer__mail" href={`mailto:${EXECUTOR_CONTACT.email}`}>
          {EXECUTOR_CONTACT.email}
        </a>
      </div>
      <p className="site-footer__note">
        Сервис анализирует состав и совместимость средств. Не является медицинской диагностикой.
      </p>
    </footer>
  )
}

export function LegalPage({ slug, onNavigate }: { slug: string; onNavigate: (path: string) => void }) {
  const doc = LEGAL_DOCS[slug]
  if (!doc) return null
  return (
    <div className="legal-shell">
      <header className="legal-header">
        <button type="button" className="legal-brand" onClick={() => onNavigate("/")}>
          айдерми
        </button>
        <button type="button" className="guest-link" onClick={() => onNavigate("/")}>
          ← На главную
        </button>
      </header>

      <main className="legal-main">
        <p className="eyebrow">Документы</p>
        <h1 className="legal-title">{doc.title}</h1>
        <p className="legal-subtitle">{doc.subtitle}</p>
        <p className="legal-status">Проект документа · версия {LEGAL_DOCS[slug]?.status === "draft" ? "draft-1" : "1"}</p>

        <div className="legal-doc">
          {doc.blocks.map((block, i) => (
            <section className="legal-block" key={i}>
              {block.h && <h2>{block.h}</h2>}
              {block.p && <p>{block.p}</p>}
              {block.ul && (
                <ul>
                  {block.ul.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
              {block.note && <p className="legal-note">{block.note}</p>}
            </section>
          ))}
        </div>

        <nav className="legal-related" aria-label="Другие документы">
          {Object.entries(LEGAL_PATHS)
            .filter(([key]) => key !== slug)
            .map(([key, title]) => (
              <button key={key} type="button" className="guest-link" onClick={() => onNavigate(`/${key}`)}>
                {title}
              </button>
            ))}
        </nav>
      </main>

      <SiteFooter onNavigate={onNavigate} />
    </div>
  )
}
