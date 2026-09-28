// Эксперимент дизайна: Soft Bubble Neo-brutalism.
// Просмотр: aidermy.ru/neo — не влияет на основной сайт.

const BORDER = '#141013'

const neo = {
  border: `2px solid ${BORDER}`,
  boxShadow: `5px 5px 0 ${BORDER}`,
} as const

const soft = {
  border: `2px solid ${BORDER}`,
  boxShadow: `4px 4px 0 ${BORDER}`,
} as const

export default function NeoPage() {
  return (
    <main className="min-h-dvh" style={{ background: '#F7F3EC' }}>
      {/* Шапка */}
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-5 md:px-6">
        <img src="/main_logo.svg" alt="aidermy" className="h-9 w-auto md:h-10" draggable={false} />
        <button
          type="button"
          className="flex items-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-bold text-white transition-transform hover:scale-[1.03] active:scale-95"
          style={{ ...neo, background: '#141013' }}
        >
          <img src="/QRCODE.svg" alt="" className="size-5" draggable={false} />
          Проверить продукт
        </button>
      </header>

      {/* Hero */}
      <section className="mx-auto w-full max-w-5xl px-4 md:px-6">
        <div className="relative overflow-hidden rounded-[2rem] px-6 py-14 text-center md:px-12" style={{ ...neo, background: '#D6F264' }}>
          <div className="pointer-events-none absolute -left-10 -top-10 size-40 rounded-full" style={{ background: '#F6CDE2', border: `2px solid ${BORDER}` }} />
          <div className="pointer-events-none absolute -right-8 top-8 size-32 rounded-full" style={{ background: '#C7DFF9', border: `2px solid ${BORDER}` }} />
          <div className="pointer-events-none absolute bottom-4 left-1/3 size-24 rounded-full" style={{ background: '#E3D7FA', border: `2px solid ${BORDER}` }} />

          <h1 className="relative font-advaken text-4xl font-normal leading-tight text-foreground md:text-6xl">
            Проверь косметику
            <br />
            за секунды
          </h1>
          <p className="relative mx-auto mt-4 max-w-md text-base text-foreground/70 md:text-lg">
            Soft Bubble Neo-brutalism — эксперимент дизайна. Найди продукт по фото и узнай, подходит ли он твоей коже.
          </p>
          <button
            type="button"
            className="relative mt-8 rounded-2xl px-8 py-4 text-base font-bold transition-transform hover:scale-[1.04] active:scale-95"
            style={{ ...soft, background: '#FFFFFF', color: '#141013' }}
          >
            Начать проверку
          </button>
        </div>

        {/* Карточки */}
        <div className="mt-6 grid gap-5 md:grid-cols-3">
          {[
            { title: 'Сфотографируй', text: 'Определим бренд и название по фото упаковки.', bg: '#C4EAD5' },
            { title: 'Найдём состав', text: 'INCI из базы или из интернета — без ручного ввода.', bg: '#C7DFF9' },
            { title: 'Получи вердикт', text: 'Совместимость с твоим типом кожи и рекомендации.', bg: '#F6CDE2' },
          ].map((f, i) => (
            <div key={i} className="rounded-[1.75rem] p-6" style={{ ...soft, background: f.bg }}>
              <div className="flex size-10 items-center justify-center rounded-full border-2 border-[#141013] bg-white text-lg font-bold">
                {i + 1}
              </div>
              <h3 className="mt-4 font-advaken text-xl text-foreground">{f.title}</h3>
              <p className="mt-2 text-sm text-foreground/70">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="mx-auto w-full max-w-5xl px-4 py-10 text-center text-xs text-foreground/50 md:px-6">
        © {new Date().getFullYear()} aidermy · эксперимент дизайна Soft Bubble Neo-brutalism
      </footer>
    </main>
  )
}
