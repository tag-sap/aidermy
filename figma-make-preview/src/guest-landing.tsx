/**
 * Гостевая страница айдерми.
 *
 * Публичная презентация продукта: профиль кожи → распознавание средства →
 * отчёт о совместимости → наборы. Никакого анализа без аккаунта здесь нет:
 * оба действия ведут в существующие модалки входа и регистрации.
 */
type GuestLandingProps = {
  onRegister: () => void
  onLogin: () => void
}

type LandingShot = {
  id: string
  base: string
  alt: string
}

const SHOTS = {
  hero: {
    id: "hero",
    base: "guest_picture_1",
    alt: "Флакон ухода с яркими стикерами в руке на фоне светлой студии",
  },
  profile: {
    id: "profile",
    base: "guest_picture_2",
    alt: "Экран телефона с заполненным профилем кожи: тип, возраст, проблемы и цели ухода",
  },
  scan: {
    id: "scan",
    base: "guest_picture_3",
    alt: "Сканирование упаковки средства камерой телефона в приложении айдерми",
  },
  report: {
    id: "report",
    base: "guest_picture_4",
    alt: "Отчёт о совместимости средства: вердикт и причины результата",
  },
  sets: {
    id: "sets",
    base: "guest_picture_5",
    alt: "Раздел наборов: несколько наборов средств с результатами проверки",
  },
} satisfies Record<string, LandingShot>

const STEPS: Array<{
  key: keyof typeof SHOTS
  index: string
  label: string
  title: string
  text: string
  tone: "plain" | "dark" | "raised" | "lime"
  reverse?: boolean
}> = [
  {
    key: "profile",
    index: "01",
    label: "Профиль",
    title: "Уход начинается с тебя",
    text: "Расскажи о своей коже, чтобы айдерми учитывал её особенности.",
    tone: "plain",
  },
  {
    key: "scan",
    index: "02",
    label: "Сканирование",
    title: "Добавляй косметику без лишних усилий",
    text: "Сфотографируй упаковку и состав, чтобы распознать средство.",
    tone: "dark",
    reverse: true,
  },
  {
    key: "report",
    index: "03",
    label: "Отчёт",
    title: "Понимай, подходит ли тебе средство",
    text: "Изучай вердикт и причины, которые стоят за результатом.",
    tone: "raised",
  },
  {
    key: "sets",
    index: "04",
    label: "Наборы",
    title: "Собери свой уход в одном месте",
    text: "Храни средства и объединяй их в наборы.",
    tone: "lime",
    reverse: true,
  },
]

function LandingPicture({ shot, priority = false }: { shot: LandingShot; priority?: boolean }) {
  return (
    <picture>
      <source srcSet={`/pictures/${shot.base}.webp`} type="image/webp" />
      <img
        className="landing-orb"
        src={`/pictures/${shot.base}.png`}
        alt={shot.alt}
        width={1024}
        height={1024}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
        {...(priority ? { fetchPriority: "high" as const } : {})}
      />
    </picture>
  )
}

export function GuestLanding({ onRegister, onLogin }: GuestLandingProps) {
  const registerButton = (
    <button type="button" className="btn btn--primary landing-cta-button" onClick={onRegister}>
      Зарегистрироваться
    </button>
  )
  const loginLink = (
    <button type="button" className="landing-link" onClick={onLogin}>
      Уже есть аккаунт? Войти
    </button>
  )

  return (
    <div className="landing">
      <header className="landing-header">
        <span className="landing-brand">айдерми</span>
        <button type="button" className="landing-link landing-link--header" onClick={onLogin}>
          Войти
        </button>
      </header>

      <div className="landing-body">
        <section className="landing-hero" aria-labelledby="landing-hero-title">
          <div className="landing-hero__inner">
            <div className="landing-hero__copy">
              <h1 id="landing-hero-title" className="landing-title">
                Помогаем выбрать уход для твоей кожи
              </h1>
              <p className="landing-hero__lead">Подбирай косметику с учётом особенностей своей кожи.</p>
              <div className="landing-actions">
                {registerButton}
                {loginLink}
              </div>
            </div>
            <div className="landing-hero__figure">
              <LandingPicture shot={SHOTS.hero} priority />
            </div>
          </div>
        </section>

        {STEPS.map((step) => {
          const headingId = `landing-step-${step.key}`
          return (
            <section
              key={step.key}
              className={`landing-step landing-step--${step.tone} ${step.reverse ? "landing-step--reverse" : ""}`}
              aria-labelledby={headingId}
            >
              <div className="landing-step__inner">
                <div className="landing-step__copy">
                  <p className="landing-step__index">
                    <span aria-hidden="true">{step.index}</span>
                    <span className="landing-step__label">{step.label}</span>
                  </p>
                  <h2 id={headingId}>{step.title}</h2>
                  <p className="landing-step__text">{step.text}</p>
                </div>
                <figure className="landing-step__figure">
                  <LandingPicture shot={SHOTS[step.key]} />
                </figure>
              </div>
            </section>
          )
        })}

        <section className="landing-final" aria-labelledby="landing-final-title">
          <div className="landing-final__panel">
            <h2 id="landing-final-title">Начни выбирать уход осознанно</h2>
            <p>Создай профиль и открой возможности айдерми.</p>
            <div className="landing-actions landing-actions--center">
              {registerButton}
              {loginLink}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
