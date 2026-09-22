'use client'

import { ArrowRight } from 'lucide-react'

interface WelcomeTabProps {
  onAuth: () => void
}

const PIPELINE = [
  { n: '01', title: 'Профиль кожи', text: 'Рассказываете о своей коже и предпочтениях.' },
  { n: '02', title: 'Проверка средств', text: 'Сканируете состав — фото, ссылка или название.' },
  { n: '03', title: 'Виртуальная полка', text: 'Собираете уход на одной полке.' },
  { n: '04', title: 'Совместимость', text: 'Видите, как вся полка работает в комплексе.' },
]

export function WelcomeTab({ onAuth }: WelcomeTabProps) {
  return (
    <div className="flex flex-col">
      {/* HERO — нативное зацикленное видео */}
      <section
        className="relative bg-[#151515]"
        style={{ width: '100vw', marginLeft: 'calc(50% - 50vw)' }}
      >
        <video
          src="/header_video.mp4"
          autoPlay
          muted
          playsInline
          loop
          preload="auto"
          className="h-[74vh] min-h-[480px] w-full object-cover"
          aria-hidden
        />
        <div className="pointer-events-none absolute inset-0 flex items-end bg-gradient-to-t from-black/75 via-black/10 to-transparent p-5 md:p-12">
          <div className="mx-auto flex w-full max-w-md flex-col gap-6 md:max-w-5xl md:flex-row md:items-end md:justify-between">
            <div className="max-w-2xl">
              <h1 className="font-[family-name:var(--font-playfair)] text-[44px] font-normal leading-[1.02] tracking-tight text-white md:text-[76px]">
                Состав решает.
                <br />
                Остальное — детали.
              </h1>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-white/85 md:text-base">
                Aidermy переводит INCI-список на язык вашей кожи и показывает, что действительно сработает, а что нет.
              </p>
            </div>
            <button
              onClick={onAuth}
              className="pointer-events-auto inline-flex shrink-0 items-center gap-2 self-start rounded-lg bg-white px-7 py-3.5 text-sm font-medium text-[#151515] shadow-[0_8px_32px_rgba(0,0,0,0.35)] transition-all hover:bg-[#F7F3EA] active:scale-[0.98] translate-y-1/2 md:self-auto"
            >
              Начать
              <ArrowRight className="size-4" />
            </button>
          </div>
        </div>
      </section>

      {/* PIPELINE — молочный фон, коралловый шрифт */}
      <section className="bg-[#F7F3EA]" style={{ width: '100vw', marginLeft: 'calc(50% - 50vw)' }}>
        <div className="mx-auto w-full max-w-md px-5 py-12 md:max-w-5xl md:py-16">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#FF4D3D]">Как это устроено</p>
          <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-4 md:gap-4">
            {PIPELINE.map((step, i) => (
              <div key={step.n} className="relative md:pr-4">
                <span className="font-[family-name:var(--font-playfair)] text-4xl font-normal text-[#FF4D3D]/35">{step.n}</span>
                <h3 className="mt-2 text-lg font-normal leading-snug text-[#FF4D3D]">{step.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-[#FF4D3D]/70">{step.text}</p>
                {i < PIPELINE.length - 1 && (
                  <ArrowRight className="mt-4 hidden size-5 text-[#FF4D3D]/40 md:block" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FOOTER — чёрный, тянется до низа */}
      <footer
        className="bg-[#151515] text-white pb-[calc(6rem+env(safe-area-inset-bottom,0px))]"
        style={{ width: '100vw', marginLeft: 'calc(50% - 50vw)' }}
      >
        <div className="mx-auto w-full max-w-md px-5 py-10 md:max-w-5xl">
          <div className="flex flex-col gap-8 md:flex-row md:justify-between">
            <div className="max-w-xs">
              <p className="font-[family-name:var(--font-playfair)] text-2xl font-normal">aidermy</p>
              <p className="mt-2 text-sm leading-relaxed text-white/60">
                Состав решает. Помогаем понимать косметику через её состав и вашу кожу.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
              <a href="#" className="text-white/70 transition-colors hover:text-white">Политика конфиденциальности</a>
              <a href="#" className="text-white/70 transition-colors hover:text-white">Условия использования</a>
              <a href="#" className="text-white/70 transition-colors hover:text-white">О проекте</a>
              <a href="mailto:lyr.ami.tag@gmail.com" className="text-white/70 transition-colors hover:text-white">Контакты</a>
              <a href="https://t.me/aidermy_news" target="_blank" rel="noopener noreferrer" className="text-white/70 transition-colors hover:text-white">Telegram</a>
            </div>
          </div>
          <div className="mt-8 border-t border-white/10 pt-5 text-xs text-white/40">
            © {new Date().getFullYear()} aidermy. Все права защищены.
          </div>
        </div>
      </footer>
    </div>
  )
}
