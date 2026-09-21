'use client'

import { ArrowRight, ScanLine, UserRound, LayoutGrid, Sparkles, FlaskConical, ShieldCheck } from 'lucide-react'
import { PingPongVideo } from '@/components/ping-pong-video'

interface WelcomeTabProps {
  onAuth: () => void
}

const FEATURES = [
  {
    icon: ScanLine,
    title: 'Разбор состава',
    text: 'Читаем INCI и объясняем роль каждого ингредиента — простым языком, без страшилок.',
  },
  {
    icon: UserRound,
    title: 'Персональный профиль',
    text: 'Тип кожи, проблемы, непереносимости. Каждая оценка — про вас, а не про «среднюю кожу».',
  },
  {
    icon: LayoutGrid,
    title: 'Моя полка',
    text: 'Соберите уход по категориям и следите за общей совместимостью состава с кожей.',
  },
  {
    icon: FlaskConical,
    title: 'Каталог',
    text: 'Тысячи средств с разобранным составом. Ищите по бренду и проверяйте за секунды.',
  },
]

const STEPS = [
  { icon: UserRound, title: 'Профиль', text: 'Расскажите о своей коже — 30 секунд.' },
  { icon: ScanLine, title: 'Состав', text: 'Фото этикетки, ссылка или название продукта.' },
  { icon: Sparkles, title: 'Итог', text: 'Процент совместимости и понятное объяснение.' },
]

export function WelcomeTab({ onAuth }: WelcomeTabProps) {
  return (
    <div className="flex flex-col">
      {/* HERO */}
      <section className="relative overflow-hidden" style={{ width: '100vw', marginLeft: 'calc(50% - 50vw)' }}>
        <PingPongVideo
          src="/header_video.mp4"
          className="h-[70vh] min-h-[420px] w-full object-cover"
        />
        <div className="pointer-events-none absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/80 via-black/25 to-black/10 p-5 md:p-12">
          <div className="mx-auto w-full max-w-md md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
            <span className="pointer-events-auto inline-flex w-fit items-center gap-1.5 rounded-full border border-white/25 bg-black/30 px-3 py-1 text-[11px] font-medium tracking-wide text-white backdrop-blur-sm">
              <Sparkles className="size-3.5 text-[#F5C900]" />
              Состав · Кожа · Осознанный выбор
            </span>
            <h1 className="mt-4 max-w-2xl font-[family-name:var(--font-playfair)] text-[40px] font-normal leading-[1.05] tracking-tight text-white md:text-[64px]">
              Состав решает.
              <br />
              Остальное — детали.
            </h1>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-white/85 md:max-w-xl md:text-base">
              Aidermy переводит INCI-список на язык вашей кожи и показывает, что действительно сработает — а что нет.
            </p>
          </div>
        </div>
      </section>

      {/* MANIFESTO */}
      <section className="px-1 py-10 text-center md:py-14">
        <p className="font-[family-name:var(--font-playfair)] text-[26px] font-normal leading-snug text-foreground md:text-[34px]">
          Мы не ставим оценки «хорошо» или «плохо».
        </p>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground md:text-base">
          Мы показываем, как состав взаимодействует именно с вашей кожей. Без рекламы, без догадок — только факты.
        </p>
        <button
          onClick={onAuth}
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-3 text-sm font-medium text-primary-foreground shadow-[0_8px_24px_rgba(18,53,45,0.35)] transition-all hover:bg-primary/90 active:scale-[0.98]"
        >
          Создать профиль
          <ArrowRight className="size-4" />
        </button>
      </section>

      {/* ЧТО УМЕЕТ */}
      <section>
        <div className="mb-4 flex items-center gap-2">
          <span className="h-px flex-1 bg-border" />
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Возможности</span>
          <span className="h-px flex-1 bg-border" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-2xl border border-border bg-white p-4 transition-colors hover:border-primary/30">
              <div className="flex size-10 items-center justify-center rounded-xl bg-primary/5 text-primary">
                <Icon className="size-5" strokeWidth={1.6} />
              </div>
              <p className="mt-3 text-[14px] font-medium text-foreground">{title}</p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground/80">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* КАК ЭТО РАБОТАЕТ */}
      <section className="mt-8">
        <div className="mb-4 flex items-center gap-2">
          <span className="h-px flex-1 bg-border" />
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Как это работает</span>
          <span className="h-px flex-1 bg-border" />
        </div>
        <div className="flex flex-col gap-3">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="flex items-center gap-4 rounded-2xl border border-border bg-white p-4">
              <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#F5C900]/20 text-[#8A6D00]">
                <Icon className="size-5" strokeWidth={1.6} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-medium text-foreground">
                  <span className="mr-1.5 font-normal text-[#B08A00]">0{i + 1}</span>
                  {title}
                </p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground/80">{text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ЧЕСТНЫЙ ИТОГ */}
      <section className="mt-8 rounded-3xl bg-primary p-6 text-white md:p-8">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 size-6 shrink-0 text-[#F5C900]" />
          <div>
            <p className="font-[family-name:var(--font-playfair)] text-xl font-normal leading-snug md:text-2xl">
              Честный разбор, а не «мнение нейросети».
            </p>
            <p className="mt-2 text-sm leading-relaxed text-white/80">
              Процент соответствия считает детерминированный движок — по ингредиентам и вашему профилю.
              ИИ лишь помогает прочитать состав на этикетке.
            </p>
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <button
        onClick={onAuth}
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl bg-primary py-4 text-sm font-medium text-primary-foreground shadow-[0_8px_24px_rgba(18,53,45,0.3)] transition-all hover:bg-primary/90 active:scale-[0.98]"
      >
        <Sparkles className="size-4 text-[#F5C900]" />
        Начать бесплатно
      </button>
    </div>
  )
}

