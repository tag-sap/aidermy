# Production rollout — 2026-10-28: новая гостевая страница, удаление гостевого анализа

## 1. Что изменено

### 1.1. Новая гостевая страница (`figma-make-preview`)

- Вместо многошагового гостевого сценария (анкета → выбор средства → сканирование →
  результат → отчёт) — одна публичная презентационная страница
  (`src/guest-landing.tsx`).
- Секции: hero («Помогаем выбрать уход для твоей кожи»), профиль, сканирование,
  отчёт, наборы, финальный призыв. Один смысл на секцию, без карточек-клонов.
- Кнопки «Зарегистрироваться» открывают существующую модалку регистрации,
  «Уже есть аккаунт? Войти» — существующую модалку входа. Отдельных маршрутов
  авторизации не появилось.
- Пять изображений: `public/pictures/guest_picture_1..5.png` + WebP-производные
  (`<picture>` с PNG-фолбэком). Hero — `loading="eager"` + `fetchpriority="high"`,
  остальные — lazy.
- Палитра и типографика — существующие токены (`--ink`, `--lime`, `--font-display`),
  кнопки — существующие `.btn`-модификаторы.

### 1.2. Удалён гостевой анализ

- Backend: удалены `app/guest_service.py`, `POST /api/guest/session`,
  `/api/guest/report`, `/api/guest/claim`, хелперы `_guest_gate`,
  `_refund_guest_check`, `_store_guest_check_result`, поля `guest_token`
  в `CheckRequest` / `CheckWithIngredientsRequest`, тест `tests/test_guest_flow.py`.
- `/api/check` и `/api/check-with-ingredients` теперь требуют авторизацию
  (`Depends(get_current_user)`): анонимный вызов возвращает 401, а не расходует
  AI-ресурсы. Авторизованная логика (списание балла, сохранение анализа,
  Phase 1/2, отчёт) не изменена.
- Frontend: удалены `GuestHomePage`, `GuestQuizScreen`, `GuestSelectScreen`,
  `GuestResultScreen`, состояние `guestStage/guestToken/guestProduct`, методы
  `api.guestSession/guestReport/guestClaim`, prop `guestToken` у `ScanPage` и
  `PhotoScan`, неиспользуемые `ParticleCanvas` и `report-details.tsx`,
  legacy-CSS гостевого сценария. Общий класс `.guest-link` сохранён — он
  используется юридическими страницами и модалками.
- `account_deletion.py` продолжает обнулять `guest_sessions.claimed_by` для
  удаляемого аккаунта: таблица с историческими строками остаётся, это гарантия
  приватности, а не логика гостевого сценария.

## 2. Проверки

- `npx tsc --noEmit` — без ошибок; `npx vite build` — успешно
  (`index-Cad7zO4Q.js`, `index-BKJpbppH.css`).
- Backend в изолированном зеркале (prod-код + изменения, отдельные БД):
  `pytest` по затронутым модулям — **88 passed**
  (`test_api_phase1`, `test_auth_registration`, `test_analysis_state`,
  `test_account_billing`, `test_evaluation_api`, `test_evaluation_app_wiring`,
  `test_frontend_scan_contract`).
- Полный прогон `pytest` в дереве production падает и **до** изменений
  (предсуществующие падения из-за состояния БД/окружения), поэтому сравнивались
  целевые наборы.
- API на production: `GET /api/health` 200, `POST /api/guest/*` → 404,
  анонимные `/api/check` и `/api/check-with-ingredients` → 401,
  `/api/auth/me` → 401, `/api/auth/login` → 405 (маршруты живы).
- E2E авторизованного сценария на production (временный аккаунт, затем удалён):
  регистрация → логин → сохранение/чтение профиля → анализ состава
  (score 71, `phase1_status=passed`, `analysis_id` создан) → отчёт
  (`report_ready=true`, review + expectations) → добавление на полку и чтение
  полки (`count=1`) → удаление аккаунта (200; повторный логин 401).
- Вёрстка: production-страница совпадает с локальной сборкой (SSIM 1.000),
  все пять изображений (PNG и WebP) отдаются с кодом 200.

## 3. Деплой

- Статика: собранный `dist` заменён в `/var/www/aidermy/figma-make-preview/dist`
  (предыдущий — в `/var/backups/aidermy/20261028_guest_landing/dist_before.tar.gz`).
- Backend: `app/main.py`, `app/models.py` обновлены, `guest_service.py` и
  `test_guest_flow.py` удалены; перезапуск — `./start.sh backend`.
  Резервные копии — в `/var/backups/aidermy/20261028_guest_landing/`.
- После перезапуска: 0 ошибок и 0 `PoolTimeout` в `aidermy_app.log`.

## 4. Важно знать

- `figma-make-preview/src` на сервере — **устаревший снимок** (не совпадает с
  задеплоенным бандлом). Он не изменялся: на сервере это чужие незакоммиченные
  файлы. Источник истины — ветка `feat/evaluation-v2`, из неё собран и задеплоен
  `dist`. Поэтому `./start.sh frontend` на сервере **нельзя** запускать, пока
  `src` не синхронизирован с веткой: он пересоберёт старую версию.
- Однофайловый Vite-бандл остаётся > 500 kB (предупреждение Vite) — как и до
  изменений; разбиение на чанки не входило в задачу.
