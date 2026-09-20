'use client'

import { ShieldCheck, Sparkles, User, LayoutGrid, Droplets, ArrowRight, CheckCircle2, FlaskConical } from 'lucide-react'

interface WelcomeTabProps {
  onAuth: () => void
}

const FEATURES = [
  {
    icon: ShieldCheck,
    title: 'Проверка состава',
    text: 'Разбираем INCI-состав и подсказываем, подходит ли продукт именно вашей коже.',
  },
  {
    icon: User,
    title: 'Твой профиль кожи',
    text: 'Заполни анкету — и каждая оценка станет персональной, а не «средней по больнице».',
  },
  {
    icon: Sparkles,
    title: 'Моя полка',
    text: 'Собери свой уход по категориям и смотри общую совместимость состава с кожей.',
  },
  {
    icon: LayoutGrid,
    title: 'Каталог косметики',
    text: 'Тысячи средств: ищи по названию, бренду или категории и проверяй в один клик.',
  },
]

const STEPS = [
  { icon: User, title: 'Заполни профиль', text: 'Тип кожи, проблемы и аллергии — 30 секунд.' },
  { icon: FlaskConical, title: 'Проверь состав', text: 'Вставь ссылку или название — AI разберёт ингредиенты.' },
  { icon: Droplets, title: 'Получи персональный итог', text: 'Оценка совместимости и понятное объяснение.' },
]

export function WelcomeTab({ onAuth }: WelcomeTabProps) {
  return (
    <div className="flex flex-col gap-6 pb-4">
      {/* HERO */}
      <section className="relative overflow-hidden rounded-3xl border border-primary/20 bg-gradient-to-br from-primary/10 via-white to-accent/10 p-6 text-center">
        <div className="pointer-events-none absolute -right-8 -top-8 size-32 rounded-full bg-primary/15 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-10 -left-6 size-28 rounded-full bg-accent/20 blur-2xl" />
        <div className="relative">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-white/70 px-3 py-1 text-[11px] font-medium text-primary">
            <Sparkles className="size-3.5" />
            AI-проверка косметики
          </span>
          <h2 className="mt-4 text-[28px] font-light leading-tight text-foreground">
            Проверяй косметику <span className="text-primary">по составу</span>,
            <br />
            а не по обещаниям
          </h2>
        </div>
      </section>

      {/* ИНТРО + CTA */}
      <section className="px-1 text-center">
        <p className="text-sm leading-relaxed text-muted-foreground/80">
          Aidermy анализирует ингредиенты и честно показывает, насколько средство
          совместимо с вашей кожей. Без рекламы и догадок — только состав.
        </p>
        <button
          onClick={onAuth}
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary px-5 py-3 text-sm font-medium text-white shadow-[0_8px_24px_rgba(78,159,110,0.35)] transition-all hover:bg-primary/90 active:scale-[0.98]"
        >
          Создать профиль и начать
          <ArrowRight className="size-4" />
        </button>
      </section>

      {/* ЧТО ЭТО */}
      <section>
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
          Что умеет Aidermy
        </h3>
        <div className="grid grid-cols-2 gap-2.5">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-2xl border border-gray-100 bg-white p-3.5 transition-colors hover:border-primary/25">
              <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="size-5" strokeWidth={1.75} />
              </div>
              <p className="mt-2.5 text-[13px] font-medium text-foreground">{title}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground/70">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* КАРТИНКА-ПРЕВЬЮ (вставьте сюда сгенерированную картинку телефона с отчётом) */}
      <section>
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
          Как выглядит отчёт
        </h3>
        {/* ЗАМЕНИТЕ содержимое ниже на: <img src="/report-phone.png" alt="Отчёт Aidermy" className="aspect-[9/16] w-full object-cover rounded-3xl" /> */}
        <div className="mx-auto flex aspect-[9/16] w-full max-w-[300px] flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-gray-200 bg-gray-50 p-6 text-center">
          <span className="text-4xl">📱</span>
          <p className="text-xs leading-relaxed text-muted-foreground/50">
            Здесь будет картинка телефона
            <br />
            с примером отчёта
          </p>
        </div>
      </section>

      {/* КАК ЭТО РАБОТАЕТ */}
      <section>
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
          Как это работает
        </h3>
        <div className="flex flex-col gap-2">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="flex items-center gap-3 rounded-2xl border border-gray-100 bg-white p-3.5">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="size-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-foreground">
                  <span className="mr-1.5 text-primary">{i + 1}.</span>
                  {title}
                </p>
                <p className="text-[11px] leading-relaxed text-muted-foreground/70">{text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ЧЕСТНЫЙ ИТОГ */}
      <section className="rounded-2xl border border-primary/20 bg-primary/5 p-4">
        <div className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" />
          <p className="text-[13px] leading-relaxed text-foreground/80">
            Каждая оценка строится на <span className="font-medium text-foreground">детерминированном движке</span> по
            ингредиентам и вашему профилю — а не на «мнении нейросети». AI лишь помогает
            разобрать состав.
          </p>
        </div>
      </section>

      {/* FINAL CTA */}
      <button
        onClick={onAuth}
        className="flex w-full items-center justify-center gap-2 rounded-2xl bg-primary py-4 text-sm font-medium text-white shadow-[0_8px_24px_rgba(78,159,110,0.3)] transition-all hover:bg-primary/90 active:scale-[0.98]"
      >
        <Sparkles className="size-4" />
        Начать бесплатно
      </button>
    </div>
  )
}
