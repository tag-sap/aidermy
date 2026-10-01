import { useMemo, useState, type ReactNode } from "react"

type Page = "home" | "catalog" | "shelf" | "scan" | "report" | "profile"
type ProductState = "saved" | "owned" | "finished"

type Product = {
  id: number
  brand: string
  name: string
  category: string
  score: number
  verdict: "Подходит" | "С осторожностью" | "Не подходит"
  image: string
  tags: string[]
  state?: ProductState
}

const products: Product[] = [
  {
    id: 1,
    brand: "COSRX",
    name: "Advanced Snail 96 Mucin Power Essence",
    category: "Эссенция",
    score: 92,
    verdict: "Подходит",
    image:
      "https://images.unsplash.com/photo-1616750819456-5cdee9b85d22?auto=format&fit=crop&w=520&q=85",
    tags: ["Увлажнение", "Восстановление"],
    state: "owned",
  },
  {
    id: 2,
    brand: "Beauty of Joseon",
    name: "Relief Sun Rice + Probiotics SPF50+",
    category: "Солнцезащита",
    score: 86,
    verdict: "Подходит",
    image:
      "https://images.unsplash.com/photo-1585652757141-8837d676fac8?auto=format&fit=crop&w=520&q=85",
    tags: ["SPF", "Без отдушки"],
    state: "saved",
  },
  {
    id: 3,
    brand: "The Ordinary",
    name: "Niacinamide 10% + Zinc 1%",
    category: "Сыворотка",
    score: 71,
    verdict: "С осторожностью",
    image:
      "https://images.unsplash.com/photo-1580870069867-74c57ee1bb07?auto=format&fit=crop&w=520&q=85",
    tags: ["Ниацинамид", "Себорегуляция"],
    state: "finished",
  },
  {
    id: 4,
    brand: "CeraVe",
    name: "Hydrating Facial Cleanser",
    category: "Очищение",
    score: 88,
    verdict: "Подходит",
    image:
      "https://images.unsplash.com/photo-1567721913486-6585f069b332?auto=format&fit=crop&w=520&q=85",
    tags: ["Церамиды", "Сухая кожа"],
  },
  {
    id: 5,
    brand: "Paula’s Choice",
    name: "Skin Perfecting 2% BHA Liquid",
    category: "Эксфолиант",
    score: 58,
    verdict: "С осторожностью",
    image:
      "https://images.unsplash.com/photo-1613803745799-ba6c10aace85?auto=format&fit=crop&w=520&q=85",
    tags: ["BHA", "Активы"],
  },
  {
    id: 6,
    brand: "Some By Mi",
    name: "AHA BHA PHA 30 Days Miracle Toner",
    category: "Тонер",
    score: 34,
    verdict: "Не подходит",
    image:
      "https://images.unsplash.com/photo-1739980155900-36562bcb7857?auto=format&fit=crop&w=520&q=85",
    tags: ["Кислоты", "Отдушка"],
  },
]

const pageNames: Record<Page, string> = {
  home: "Главная",
  catalog: "Каталог",
  shelf: "Моя полка",
  scan: "Сканировать",
  report: "Отчёт",
  profile: "Профиль кожи",
}

function Icon({
  name,
  size = 20,
}: {
  name: "home" | "search" | "shelf" | "report" | "scan" | "plus" | "arrow" | "chevron" | "close" | "check" | "bookmark" | "box" | "history" | "filter" | "more" | "info" | "profile" | "drop"
  size?: number
}) {
  const paths: Record<string, ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7" />
        <path d="M5 9v11h14V9M9 20v-6h6v6" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    shelf: (
      <>
        <path d="M4 4h6v16H4zM14 4h6v16h-6z" />
        <path d="M6.5 8h1M16.5 8h1" />
      </>
    ),
    report: (
      <>
        <path d="M5 20V10M12 20V4M19 20v-7" />
        <path d="M3 20h18" />
      </>
    ),
    scan: (
      <>
        <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
        <path d="M8 12h8" />
      </>
    ),
    plus: (
      <>
        <path d="M12 5v14M5 12h14" />
      </>
    ),
    arrow: <path d="m5 12 14 0m-5-5 5 5-5 5" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    check: <path d="m5 12 4 4L19 6" />,
    bookmark: <path d="M6 4h12v17l-6-4-6 4z" />,
    box: (
      <>
        <path d="m4 7 8-4 8 4v10l-8 4-8-4z" />
        <path d="m4 7 8 4 8-4M12 11v10" />
      </>
    ),
    history: (
      <>
        <path d="M4 12a8 8 0 1 0 2-5.3L4 9" />
        <path d="M4 4v5h5M12 8v5l3 2" />
      </>
    ),
    filter: (
      <>
        <path d="M4 6h16M7 12h10M10 18h4" />
      </>
    ),
    more: (
      <>
        <circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" />
        <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        <circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7h.01" />
      </>
    ),
    profile: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4.5 20c.7-4 3.2-6 7.5-6s6.8 2 7.5 6" />
      </>
    ),
    drop: <path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11Z" />,
  }
  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      <g
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      >
        {paths[name]}
      </g>
    </svg>
  )
}

function Button({
  children,
  variant = "primary",
  onClick,
  className = "",
}: {
  children: ReactNode
  variant?: "primary" | "secondary" | "ghost" | "icon"
  onClick?: () => void
  className?: string
}) {
  return (
    <button
      className={`button button--${variant} ${className}`}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode
  tone?: string
}) {
  return <span className={`badge badge--${tone}`}>{children}</span>
}

function Score({ value, large = false }: { value: number large?: boolean }) {
  const tone = value >= 80 ? "good" : value >= 50 ? "warn" : "bad"
  return (
    <span className={`score score--${tone} ${large ? "score--large" : ""}`}>
      {value}
    </span>
  )
}

function Verdict({ value }: { value: Product["verdict"] }) {
  const tone =
    value === "Подходит" ? "good" : value === "С осторожностью" ? "warn" : "bad"
  return (
    <Badge tone={tone}>
      <span className="badge-dot" />
      {value}
    </Badge>
  )
}

function Search({
  value,
  onChange,
  placeholder = "Найти по названию, бренду или ингредиенту",
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <label className="search">
      <Icon name="search" />
      <input
        aria-label="Поиск"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type="search"
        value={value}
      />
      <kbd>⌘ K</kbd>
    </label>
  )
}

function Tabs({
  items,
  active,
  onChange,
}: {
  items: { id: string label: string count?: number }[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          className={active === item.id ? "tab tab--active" : "tab"}
          key={item.id}
          onClick={() => onChange(item.id)}
          role="tab"
          type="button"
        >
          {item.label}
          {item.count !== undefined && <span>{item.count}</span>}
        </button>
      ))}
    </div>
  )
}

function ProductCard({
  product,
  onOpen,
  onStateChange,
}: {
  product: Product
  onOpen: () => void
  onStateChange: (state: ProductState) => void
}) {
  const stateLabels: Record<ProductState, string> = {
    saved: "Хочу попробовать",
    owned: "Сейчас использую",
    finished: "Закончилось",
  }
  return (
    <article className="product-card">
      <button className="product-card__open" onClick={onOpen} type="button">
        <div className="product-card__image">
          <img alt="" src={product.image} />
          <Score value={product.score} />
        </div>
        <div className="product-card__content">
          <p className="eyebrow">{product.brand}</p>
          <h3>{product.name}</h3>
          <p className="muted">{product.category}</p>
          <Verdict value={product.verdict} />
        </div>
      </button>
      {product.state ? (
        <button
          className={`state-control state-control--${product.state}`}
          onClick={() =>
            onStateChange(
              product.state === "saved"
                ? "owned"
                : product.state === "owned"
                  ? "finished"
                  : "saved",
            )
          }
          type="button"
        >
          <Icon
            name={
              product.state === "saved"
                ? "bookmark"
                : product.state === "owned"
                  ? "box"
                  : "history"
            }
            size={16}
          />
          {stateLabels[product.state]}
          <Icon name="chevron" size={15} />
        </button>
      ) : (
        <Button
          className="product-card__add"
          onClick={() => onStateChange("saved")}
          variant="secondary"
        >
          <Icon name="plus" size={16} />
          На полку
        </Button>
      )}
    </article>
  )
}

function Header({
  page,
  query,
  setQuery,
  onNavigate,
}: {
  page: Page
  query: string
  setQuery: (value: string) => void
  onNavigate: (page: Page) => void
}) {
  return (
    <header className="topbar">
      <div className="mobile-title">
        <span className="logo-mark">A</span>
        <strong>Aidermy</strong>
      </div>
      <div className="topbar__title">
        <p className="eyebrow">Рабочее пространство</p>
        <strong>{pageNames[page]}</strong>
      </div>
      <Search onChange={setQuery} value={query} />
      <Button
        className="scan-button"
        onClick={() => onNavigate("scan")}
        variant="secondary"
      >
        <Icon name="scan" />
        Сканировать
      </Button>
      <button aria-label="Профиль" className="avatar" type="button">
        АК
      </button>
    </header>
  )
}

function Sidebar({
  page,
  onNavigate,
}: {
  page: Page
  onNavigate: (page: Page) => void
}) {
  const navItems: {
    id: Page
    icon: Parameters<typeof Icon>[0]["name"]
    label: string
  }[] = [
    { id: "home", icon: "home", label: "Главная" },
    { id: "shelf", icon: "shelf", label: "Моя полка" },
    { id: "scan", icon: "scan", label: "Сканировать" },
    { id: "catalog", icon: "search", label: "Каталог" },
    { id: "profile", icon: "profile", label: "Профиль" },
  ]
  const mobileNavItems: {
    id: Page | "scan"
    icon: Parameters<typeof Icon>[0]["name"]
    label: string
  }[] = [
    { id: "home", icon: "home", label: "Главная" },
    { id: "shelf", icon: "shelf", label: "Полка" },
    { id: "scan", icon: "scan", label: "Сканировать" },
    { id: "catalog", icon: "search", label: "Каталог" },
    { id: "profile", icon: "profile", label: "Профиль" },
  ]
  return (
    <>
      <aside className="sidebar">
        <div className="brand">
          <span className="logo-mark">A</span>
          <strong>Aidermy</strong>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              className={
                page === item.id ? "nav-item nav-item--active" : "nav-item"
              }
              key={item.id}
              onClick={() => onNavigate(item.id)}
              type="button"
            >
              <Icon name={item.icon} />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-card">
          <span className="sidebar-card__icon">
            <Icon name="scan" />
          </span>
          <strong>Быстрая проверка</strong>
          <p>Сфотографируйте состав — разберём за минуту.</p>
          <Button onClick={() => onNavigate("scan")} variant="secondary">
            Открыть сканер
          </Button>
        </div>
        <div className="profile-mini">
          <span className="avatar">АК</span>
          <span>
            <strong>Анна К.</strong>
            <small>Комбинированная кожа</small>
          </span>
          <Icon name="more" />
        </div>
      </aside>
      <nav className="bottom-nav">
        {mobileNavItems.map((item) => (
          <button
            className={
              item.id === "scan"
                ? "bottom-nav__item bottom-nav__item--scan"
                : page === item.id
                  ? "bottom-nav__item bottom-nav__item--active"
                  : "bottom-nav__item"
            }
            key={item.id}
            onClick={() => onNavigate(item.id)}
            type="button"
          >
            <span className="bottom-nav__icon">
              <Icon name={item.icon} />
            </span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </>
  )
}

function HomePage({
  onNavigate,
  onOpen,
}: {
  onNavigate: (page: Page) => void
  onOpen: (p: Product) => void
}) {
  return (
    <div className="page-stack">
      <section className="welcome-row">
        <div>
          <p className="eyebrow">Ваше пространство ухода</p>
          <h1>Доброе утро, Анна</h1>
          <p className="lead">
            Проверяйте косметику с учётом того, что важно именно вашей коже.
          </p>
        </div>
        <Button
          className="home-scan-button"
          onClick={() => onNavigate("scan")}
        >
          <Icon name="scan" /> Сканировать состав
        </Button>
      </section>

      <section className="home-hero-grid">
        <article className="skin-profile-card">
          <div className="skin-profile-card__head">
            <span className="skin-profile-card__icon">
              <Icon name="profile" size={24} />
            </span>
            <div>
              <p className="eyebrow">Профиль кожи</p>
              <h2>Комбинированная, чувствительная</h2>
            </div>
            <Button onClick={() => onNavigate("profile")} variant="ghost">
              Изменить <Icon name="chevron" size={16} />
            </Button>
          </div>
          <div className="profile-factors">
            <span>
              <small>Основные цели</small>
              <strong>Барьер · Увлажнение</strong>
            </span>
            <span>
              <small>Чувствительность</small>
              <strong>Повышенная</strong>
            </span>
            <span>
              <small>Избегать</small>
              <strong>Отдушки · Спирт</strong>
            </span>
          </div>
          <p className="profile-note">
            Match каждого продукта рассчитывается по этому профилю и вашей
            текущей полке.
          </p>
        </article>
        <article className="scan-card">
          <span className="scan-card__icon">
            <Icon name="scan" size={28} />
          </span>
          <div>
            <p className="eyebrow">Быстрая проверка</p>
            <h2>Узнайте, подходит ли состав</h2>
            <p>Наведите камеру на этикетку или загрузите фотографию.</p>
          </div>
          <Button onClick={() => onNavigate("scan")}>
            Открыть сканер <Icon name="arrow" />
          </Button>
        </article>
      </section>

      <section className="metrics-grid metrics-grid--home">
        <article className="metric metric--accent">
          <div>
            <p>На полке</p>
            <strong>12</strong>
            <small>3 заканчиваются</small>
          </div>
          <span>
            <Icon name="shelf" size={24} />
          </span>
        </article>
        <article className="metric">
          <div>
            <p>Средний Match</p>
            <strong>84</strong>
            <small className="positive">+6 за месяц</small>
          </div>
          <span>
            <Icon name="report" size={24} />
          </span>
        </article>
        <article className="metric">
          <div>
            <p>Разобрано</p>
            <strong>37</strong>
            <small>продуктов</small>
          </div>
          <span>
            <Icon name="check" size={24} />
          </span>
        </article>
      </section>

      <div className="content-grid">
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Последние проверки</p>
              <h2>Недавно разобрали</h2>
            </div>
            <Button onClick={() => onNavigate("catalog")} variant="ghost">
              Все продукты <Icon name="arrow" />
            </Button>
          </div>
          <div className="compact-list">
            {products.slice(0, 3).map((product) => (
              <button
                className="compact-product"
                key={product.id}
                onClick={() => onOpen(product)}
                type="button"
              >
                <img alt="" src={product.image} />
                <span>
                  <strong>{product.name}</strong>
                  <small>
                    {product.brand} · {product.category}
                  </small>
                </span>
                <Verdict value={product.verdict} />
                <Score value={product.score} />
                <Icon name="chevron" />
              </button>
            ))}
          </div>
        </section>

        <aside className="panel routine">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Моя полка</p>
              <h2>Статус ухода</h2>
            </div>
            <Badge tone="good">10 из 12 подходят</Badge>
          </div>
          {["Очищение", "Тонер", "Сыворотка", "Увлажнение"].map(
            (step, index) => (
              <div className="routine-step" key={step}>
                <span
                  className={
                    index < 2 ? "step-number step-number--done" : "step-number"
                  }
                >
                  {index < 2 ? <Icon name="check" size={14} /> : index + 1}
                </span>
                <span>
                  <strong>{step}</strong>
                  <small>
                    {index === 0
                      ? "CeraVe Cleanser"
                      : index === 1
                        ? "Pyunkang Yul"
                        : index === 2
                          ? "The Ordinary"
                          : "COSRX Snail 96"}
                  </small>
                </span>
                <Icon name="chevron" size={16} />
              </div>
            ),
          )}
        </aside>
      </div>
    </div>
  )
}

function CatalogPage({
  items,
  onOpen,
  onStateChange,
  onNavigate,
}: {
  items: Product[]
  onOpen: (p: Product) => void
  onStateChange: (id: number, state: ProductState) => void
  onNavigate: (page: Page) => void
}) {
  const [active, setActive] = useState("all")
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">База продуктов</p>
          <h1>Каталог косметики</h1>
          <p className="lead">
            Проверяйте составы и находите продукты под особенности вашей кожи.
          </p>
        </div>
        <Button onClick={() => onNavigate("scan")}>
          <Icon name="scan" /> Проверить состав
        </Button>
      </section>
      <Tabs
        active={active}
        items={[
          { id: "all", label: "Все", count: 1284 },
          { id: "face", label: "Для лица", count: 743 },
          { id: "spf", label: "SPF", count: 186 },
          { id: "clean", label: "Очищение", count: 212 },
          { id: "body", label: "Для тела", count: 143 },
        ]}
        onChange={setActive}
      />
      <div className="catalog-toolbar">
        <p>
          <strong>{items.length} продуктов</strong>
          <span>Подобраны с учётом вашего профиля</span>
        </p>
        <div>
          <Button variant="secondary">
            <Icon name="filter" /> Фильтры <Badge>2</Badge>
          </Button>
          <Button variant="secondary">
            По совместимости <Icon name="chevron" size={16} />
          </Button>
        </div>
      </div>
      {items.length > 0 ? (
        <div className="product-grid">
          {items.map((product) => (
            <ProductCard
              key={product.id}
              onOpen={() => onOpen(product)}
              onStateChange={(state) => onStateChange(product.id, state)}
              product={product}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Ничего не найдено"
          text="Попробуйте изменить запрос или сбросить фильтры."
        />
      )}
    </div>
  )
}

function ShelfPage({
  items,
  onOpen,
  onStateChange,
}: {
  items: Product[]
  onOpen: (p: Product) => void
  onStateChange: (id: number, state: ProductState) => void
}) {
  const [active, setActive] = useState("all")
  const [category, setCategory] = useState("Все")
  const categories = [
    "Все",
    "Очищение",
    "Тонер",
    "Сыворотка",
    "Эссенция",
    "SPF",
  ]
  const byStatus =
    active === "all" ? items : items.filter((item) => item.state === active)
  const visible =
    category === "Все"
      ? byStatus
      : byStatus.filter((item) =>
          category === "SPF"
            ? item.category === "Солнцезащита"
            : item.category === category,
        )
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Ваши средства</p>
          <h1>Моя полка</h1>
          <p className="lead">
            Соберите уход по этапам и следите за статусом каждого продукта.
          </p>
        </div>
        <Button>
          <Icon name="plus" /> Добавить продукт
        </Button>
      </section>
      <Tabs
        active={active}
        items={[
          { id: "all", label: "Все", count: items.length },
          {
            id: "owned",
            label: "Сейчас использую",
            count: items.filter((p) => p.state === "owned").length,
          },
          {
            id: "saved",
            label: "Хочу попробовать",
            count: items.filter((p) => p.state === "saved").length,
          },
          {
            id: "finished",
            label: "Закончилось",
            count: items.filter((p) => p.state === "finished").length,
          },
        ]}
        onChange={setActive}
      />
      <div className="shelf-categories" aria-label="Категории ухода">
        {categories.map((item) => {
          const count =
            item === "Все"
              ? items.length
              : items.filter((product) =>
                  item === "SPF"
                    ? product.category === "Солнцезащита"
                    : product.category === item,
                ).length
          return (
            <button
              className={
                category === item
                  ? "category-chip category-chip--active"
                  : "category-chip"
              }
              key={item}
              onClick={() => setCategory(item)}
              type="button"
            >
              <span className="category-chip__icon">
                <Icon
                  name={
                    item === "Все" ? "shelf" : item === "SPF" ? "check" : "drop"
                  }
                  size={18}
                />
              </span>
              <span>
                <strong>{item}</strong>
                <small>{count} продуктов</small>
              </span>
            </button>
          )
        })}
      </div>
      <div className="shelf-summary">
        <div>
          <span className="summary-icon">
            <Icon name="info" />
          </span>
          <p>
            <strong>Полка выглядит хорошо</strong>
            <small>
              10 из 12 продуктов подходят вашему профилю. Проверьте 2 средства с
              активами.
            </small>
          </p>
        </div>
        <Button variant="ghost">
          Посмотреть рекомендации <Icon name="arrow" />
        </Button>
      </div>
      {visible.length ? (
        <div className="product-grid">
          {visible.map((product) => (
            <ProductCard
              key={product.id}
              onOpen={() => onOpen(product)}
              onStateChange={(state) => onStateChange(product.id, state)}
              product={product}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Здесь пока пусто"
          text="Добавьте продукт или перенесите его из другой категории."
        />
      )}
    </div>
  )
}

function ScanPage({ onComplete }: { onComplete: () => void }) {
  const [method, setMethod] = useState<"photo" | "text">("photo")
  const [fileName, setFileName] = useState("")
  const [ingredients, setIngredients] = useState("")

  const canAnalyze = method === "photo" ? Boolean(fileName) : ingredients.trim().length > 20

  return (
    <div className="page-stack scan-page">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Новая проверка</p>
          <h1>Сканировать состав</h1>
          <p className="lead">
            Добавьте фото этикетки или вставьте список INCI — Aidermy сопоставит
            формулу с вашим профилем и полкой.
          </p>
        </div>
        <Badge tone="good">Профиль активен</Badge>
      </section>

      <div className="scan-workspace">
        <section className="scan-stage">
          <div className="scan-methods" role="tablist">
            <button
              className={method === "photo" ? "scan-method scan-method--active" : "scan-method"}
              onClick={() => setMethod("photo")}
              role="tab"
              type="button"
            >
              <Icon name="scan" size={18} />
              Фото состава
            </button>
            <button
              className={method === "text" ? "scan-method scan-method--active" : "scan-method"}
              onClick={() => setMethod("text")}
              role="tab"
              type="button"
            >
              <Icon name="report" size={18} />
              Вставить INCI
            </button>
          </div>

          {method === "photo" ? (
            <div className={fileName ? "scan-dropzone scan-dropzone--ready" : "scan-dropzone"}>
              <span className="scan-frame" aria-hidden="true">
                <span />
                <Icon name={fileName ? "check" : "scan"} size={34} />
              </span>
              <div>
                <p className="eyebrow">{fileName ? "Фото готово" : "Этикетка с составом"}</p>
                <h2>{fileName || "Расположите список ингредиентов в кадре"}</h2>
                <p>
                  {fileName
                    ? "Проверьте, что текст виден целиком, и запустите анализ."
                    : "Подойдёт чёткое фото в JPG, PNG или HEIC без бликов."}
                </p>
              </div>
              <label className="button button--secondary upload-control">
                <Icon name="plus" size={17} />
                {fileName ? "Заменить фото" : "Загрузить фото"}
                <input
                  accept="image/*"
                  onChange={(event) => setFileName(event.target.files?.[0]?.name || "")}
                  type="file"
                />
              </label>
            </div>
          ) : (
            <label className="inci-field">
              <span>
                <strong>Список ингредиентов</strong>
                <small>{ingredients.length} символов</small>
              </span>
              <textarea
                onChange={(event) => setIngredients(event.target.value)}
                placeholder="Aqua, Glycerin, Niacinamide, Panthenol..."
                value={ingredients}
              />
            </label>
          )}

          <div className="scan-action">
            <span>
              <Icon name="info" size={17} />
              Фото используется только для распознавания состава
            </span>
            <Button
              className={!canAnalyze ? "button--disabled" : ""}
              onClick={canAnalyze ? onComplete : undefined}
            >
              Анализировать состав <Icon name="arrow" />
            </Button>
          </div>
        </section>

        <aside className="scan-aside">
          <p className="eyebrow">Что учтём</p>
          <h2>Персональный контекст</h2>
          <div className="scan-context-list">
            <article>
              <span><Icon name="profile" /></span>
              <div>
                <strong>Профиль кожи</strong>
                <small>Комбинированная · чувствительная</small>
              </div>
              <Icon name="check" size={17} />
            </article>
            <article>
              <span><Icon name="drop" /></span>
              <div>
                <strong>Цели ухода</strong>
                <small>Барьер · увлажнение · ровный тон</small>
              </div>
              <Icon name="check" size={17} />
            </article>
            <article>
              <span><Icon name="shelf" /></span>
              <div>
                <strong>Текущая полка</strong>
                <small>12 средств · проверка конфликтов</small>
              </div>
              <Icon name="check" size={17} />
            </article>
          </div>
          <div className="scan-tip">
            <span>01</span>
            <p>
              <strong>Для точного результата</strong>
              <small>Снимайте состав прямо, при ровном свете и без обрезанных строк.</small>
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}

function ReportPage({ product }: { product: Product }) {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Персональный разбор продукта</p>
          <h1>Отчёт о продукте</h1>
          <p className="lead">
            Состав разобран с учётом вашего профиля кожи и текущего ухода.
          </p>
        </div>
        <Button variant="secondary">Сохранить отчёт</Button>
      </section>
      <section className="product-report-hero">
        <img alt="" src={product.image} />
        <div className="product-report-hero__copy">
          <p className="eyebrow">
            {product.brand} · {product.category}
          </p>
          <h2>{product.name}</h2>
          <div className="report-verdict">
            <Score large value={product.score} />
            <span>
              <Verdict value={product.verdict} />
              <strong>Высокий Match с вашим профилем</strong>
              <small>
                Поддерживает барьер и не конфликтует с продуктами на полке.
              </small>
            </span>
          </div>
        </div>
        <div className="report-context">
          <p className="eyebrow">Основа анализа</p>
          <span>
            <Icon name="profile" size={17} /> Комбинированная кожа
          </span>
          <span>
            <Icon name="drop" size={17} /> Чувствительность
          </span>
          <span>
            <Icon name="shelf" size={17} /> 12 средств на полке
          </span>
        </div>
      </section>
      <section className="report-summary-grid">
        <article>
          <span>01</span>
          <div>
            <small>Барьер кожи</small>
            <strong>Поддерживает</strong>
          </div>
          <Badge tone="good">Сильная сторона</Badge>
        </article>
        <article>
          <span>02</span>
          <div>
            <small>Риск реакции</small>
            <strong>Низкий</strong>
          </div>
          <Badge tone="good">Без отдушки</Badge>
        </article>
        <article>
          <span>03</span>
          <div>
            <small>Совместимость</small>
            <strong>Конфликтов нет</strong>
          </div>
          <Badge>С вашей полкой</Badge>
        </article>
      </section>
      <div className="report-grid product-report-grid">
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Формула</p>
              <h2>Что работает для вашей кожи</h2>
            </div>
            <Badge>{product.tags.length + 3} ключевых компонентов</Badge>
          </div>
          <div className="report-ingredient-list">
            {[
              [
                "Муцин улитки, 96%",
                "Увлажняет и помогает восстановлению",
                "Подходит",
              ],
              ["Бетаин", "Снижает потерю влаги", "Подходит"],
              ["Пантенол", "Успокаивает чувствительную кожу", "Подходит"],
              ["Аргинин", "Поддерживает защитный барьер", "Нейтрально"],
            ].map(([name, description, status], index) => (
              <div key={name}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>
                  <strong>{name}</strong>
                  <small>{description}</small>
                </p>
                <Badge tone={status === "Подходит" ? "good" : "neutral"}>
                  {status}
                </Badge>
              </div>
            ))}
          </div>
        </section>
        <aside className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Применение</p>
              <h2>Как встроить в уход</h2>
            </div>
          </div>
          <div className="insight">
            <span>01</span>
            <p>
              <strong>После тонера</strong>
              <small>Нанесите 1–2 нажатия на слегка влажную кожу.</small>
            </p>
          </div>
          <div className="insight">
            <span>02</span>
            <p>
              <strong>Утром и вечером</strong>
              <small>Можно использовать ежедневно, затем закрыть кремом.</small>
            </p>
          </div>
          <div className="report-note">
            <Icon name="info" size={18} />
            <p>
              <strong>Учтено в отчёте</strong>
              <small>
                На полке нет активов, конфликтующих с этой эссенцией.
              </small>
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}

function ProfilePage() {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Персонализация Match</p>
          <h1>Профиль кожи</h1>
          <p className="lead">
            Эти данные используются при разборе каждого состава.
          </p>
        </div>
        <Button variant="secondary">Редактировать</Button>
      </section>
      <section className="profile-page-grid">
        <article className="panel profile-overview">
          <span className="profile-overview__mark">АК</span>
          <div>
            <p className="eyebrow">Текущий профиль</p>
            <h2>Комбинированная кожа</h2>
            <p className="lead">
              Повышенная чувствительность · обновлён 12 мая
            </p>
          </div>
        </article>
        <article className="panel profile-detail">
          <p className="eyebrow">Цели ухода</p>
          <h2>Барьер и увлажнение</h2>
          <div>
            <Badge tone="good">Восстановление</Badge>
            <Badge>Ровный тон</Badge>
            <Badge>Комфорт</Badge>
          </div>
        </article>
        <article className="panel profile-detail">
          <p className="eyebrow">Особенности</p>
          <h2>На что смотрит Aidermy</h2>
          <div>
            <Badge tone="warn">Чувствительность</Badge>
            <Badge tone="bad">Отдушки</Badge>
            <Badge tone="bad">Сушащий спирт</Badge>
          </div>
        </article>
      </section>
    </div>
  )
}

function EmptyState({ title, text }: { title: string text: string }) {
  return (
    <div className="empty-state">
      <span>
        <Icon name="search" size={26} />
      </span>
      <h2>{title}</h2>
      <p>{text}</p>
      <Button variant="secondary">Сбросить фильтры</Button>
    </div>
  )
}

function ProductModal({
  product,
  onClose,
}: {
  product: Product
  onClose: () => void
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose} role="presentation">
      <div
        aria-modal="true"
        className="modal"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="modal__header">
          <Badge>Карточка продукта</Badge>
          <Button onClick={onClose} variant="icon">
            <Icon name="close" />
          </Button>
        </div>
        <div className="modal__product">
          <img alt="" src={product.image} />
          <div>
            <p className="eyebrow">{product.brand}</p>
            <h2>{product.name}</h2>
            <p className="muted">{product.category} · 100 мл</p>
            <div className="modal__verdict">
              <Score large value={product.score} />
              <span>
                <Verdict value={product.verdict} />
                <small>Совместимость с вашим профилем</small>
              </span>
            </div>
          </div>
        </div>
        <div className="modal__tabs">
          <button className="active" type="button">
            Обзор
          </button>
          <button type="button">Состав</button>
          <button type="button">Как использовать</button>
        </div>
        <div className="modal__body">
          <section>
            <h3>Почему подходит</h3>
            <ul className="check-list">
              <li>
                <Icon name="check" size={16} />
                <span>
                  <strong>Поддерживает защитный барьер</strong>
                  <small>
                    Церамиды и увлажняющие компоненты подходят вашему типу кожи.
                  </small>
                </span>
              </li>
              <li>
                <Icon name="check" size={16} />
                <span>
                  <strong>Без конфликтов с рутиной</strong>
                  <small>Можно сочетать с продуктами на вашей полке.</small>
                </span>
              </li>
            </ul>
          </section>
          <section>
            <h3>Ключевые компоненты</h3>
            <div className="ingredient-list">
              {["Ниацинамид", "Пантенол", "Гиалуроновая кислота"].map(
                (name, index) => (
                  <div key={name}>
                    <span>{index + 1}</span>
                    <p>
                      <strong>{name}</strong>
                      <small>
                        {index === 0
                          ? "Выравнивает тон"
                          : index === 1
                            ? "Успокаивает"
                            : "Удерживает влагу"}
                      </small>
                    </p>
                    <Badge tone="good">OK</Badge>
                  </div>
                ),
              )}
            </div>
          </section>
        </div>
        <div className="modal__footer">
          <Button variant="secondary">
            <Icon name="bookmark" /> Сохранить
          </Button>
          <Button>
            <Icon name="plus" /> Добавить на полку
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [page, setPage] = useState<Page>("home")
  const [query, setQuery] = useState("")
  const [selected, setSelected] = useState<Product | null>(null)
  const [items, setItems] = useState(products)

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return items
    return items.filter((item) =>
      [item.name, item.brand, item.category, ...item.tags]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    )
  }, [items, query])

  function changeState(id: number, state: ProductState) {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, state } : item)),
    )
  }

  function navigate(next: Page) {
    setPage(next)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  return (
    <div className="app-shell">
      <Sidebar onNavigate={navigate} page={page} />
      <div className="workspace">
        <Header
          onNavigate={navigate}
          page={page}
          query={query}
          setQuery={setQuery}
        />
        <main className="main-content">
          {page === "home" && (
            <HomePage onNavigate={navigate} onOpen={setSelected} />
          )}
          {page === "catalog" && (
            <CatalogPage
              items={filtered}
              onNavigate={navigate}
              onOpen={setSelected}
              onStateChange={changeState}
            />
          )}
          {page === "shelf" && (
            <ShelfPage
              items={filtered.filter((item) => item.state)}
              onOpen={setSelected}
              onStateChange={changeState}
            />
          )}
          {page === "scan" && (
            <ScanPage onComplete={() => navigate("report")} />
          )}
          {page === "report" && <ReportPage product={items[0]} />}
          {page === "profile" && <ProfilePage />}
        </main>
      </div>
      {selected && (
        <ProductModal onClose={() => setSelected(null)} product={selected} />
      )}
    </div>
  )
}
