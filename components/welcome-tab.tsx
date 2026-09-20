'use client'

import { ShieldCheck, Sparkles, User, LayoutGrid, Droplets, ArrowRight, CheckCircle2, FlaskConical, AlertCircle } from 'lucide-react'
import { AdHero } from './ad-hero'

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

const SAMPLE_REPORT = {
  brand: 'CeraVe',
  name: 'Увлажняющий крем с церамидами',
  score: 87,
  verdict: 'Подходит',
  summary: 'Формула в целом соответствует вашему профилю чувствительной кожи и поддерживает увлажнение.',
  safe: ['Глицерин', 'Церамиды', 'Пантенол', 'Гиалуроновая кислота'],
  caution: ['Отдушка'],
}

function MiniScoreRing({ score }: { score: number }) {
  const size = 64
  const stroke = 5
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference

  return (
    <div className="relative flex size-16 shrink-0 items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#4E9F6E" strokeOpacity={0.12} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#4E9F6E"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-sm font-semibold text-[#4E9F6E]">{score}%</span>
      </div>
    </div>
  )
}

export function WelcomeTab({ onAuth }: WelcomeTabProps) {
  return (
    <div className="flex flex-col gap-6 pb-4">
      {/* HERO — фирменный дизайн AIdermy */}
      <AdHero />

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

      {/* ПРИМЕР ОТЧЁТА */}
      <section>
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
          Пример отчёта
        </h3>
        <div className="rounded-3xl border border-gray-100 bg-white p-4 shadow-[0_8px_32px_rgba(78,159,110,0.08)]">
          <div className="flex items-center gap-3">
            <MiniScoreRing score={SAMPLE_REPORT.score} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[9px] uppercase tracking-wide text-muted-foreground/50">{SAMPLE_REPORT.brand}</p>
              <p className="text-sm font-medium leading-snug text-foreground">{SAMPLE_REPORT.name}</p>
              <span className="mt-1.5 inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                {SAMPLE_REPORT.verdict}
              </span>
            </div>
          </div>

          <p className="mt-3 break-words text-xs leading-relaxed text-foreground/70">{SAMPLE_REPORT.summary}</p>

          <div className="mt-3 space-y-2">
            <div>
              <p className="mb-1 text-[10px] font-medium text-[#4E9F6E]">Подходящие ингредиенты</p>
              <div className="flex flex-wrap gap-1">
                {SAMPLE_REPORT.safe.map((i) => (
                  <span key={i} className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-[#4E9F6E]">{i}</span>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-1 text-[10px] font-medium text-orange-600">Требует внимания</p>
              <div className="flex flex-wrap gap-1">
                {SAMPLE_REPORT.caution.map((i) => (
                  <span key={i} className="flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[10px] text-red-500">
                    <AlertCircle className="size-2.5" />
                    {i}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
        <p className="mt-2 text-center text-[10px] text-muted-foreground/40">
          Такой персональный отчёт вы получите по каждому продукту
        </p>
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
