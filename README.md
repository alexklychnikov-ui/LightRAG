# LightRAG + Telegram Bot (RU)

Проект: интеграция Telegram-бота с LightRAG для:
- пополнения БЗ (текст, файл, URL),
- Q&A по базе знаний,
- трекинга обработки документов,
- авто-перевода на русский (опционально).

## Что реализовано

- Telegram меню с режимами: `Пополнить БЗ`, `Задать вопрос`, `Статус`.
- Ingest:
  - текст,
  - файл (`/documents/upload`, fallback на `/documents/file`),
  - URL (парсинг страницы + извлечение значимого контента).
- Q&A:
  - стартовый режим + fallback (`mix -> hybrid -> global`),
  - выбор режима через `/qmode` и кнопки,
  - inline override: `режим:<mode> | вопрос`.
- Track status:
  - уведомления `обрабатывается -> обработан/ошибка`.
- Надежность:
  - rate-limit по чату,
  - retry HTTP с учетом `Retry-After` для `429`,
  - безопасно без retry для ingest POST (чтобы не дублировать документы),
  - централизованный error handler,
  - runtime-метрики в режиме `Статус`.
- Авто-перевод на RU:
  - для текста, URL и текстовых файлов,
  - с сохранением технических идентификаторов (команды, ноды, API, URL, параметры).

## Структура

- `telegram_bot/` — код бота.
- `tests/` — unit tests.
- `Documentation/lightrag_guide.md` — рабочий гайд и версионный лог этапов.
- `.agent-remote/` — скрипты удаленного деплоя/операций.

## Переменные окружения

Минимум:
- `TELEGRAM_BOT_TOKEN`
- `LIGHTRAG_URL`
- `LIGHTRAG_API_KEY`

Опционально:
- `TELEGRAM_BOT_CHATID`
- `BOT_TRANSLATE_TO_RU=true|false`
- `BOT_QUERY_MODE=mix|hybrid|global|local|naive`
- `BOT_QUERY_FALLBACK_MODES=hybrid,global`
- `BOT_ENABLE_OPENAI_FALLBACK=true|false` (если `true`, после слабого ответа RAG идет прямой запрос к модели)
- `OPENAI_API_KEY` (нужен для fallback вне RAG)
- `BOT_OPENAI_MODEL=gpt-4o-mini`
- `OPENAI_API_BASE_URL=https://api.openai.com/v1` (опционально для кастомного провайдера)
- `BOT_RATE_LIMIT_MAX_EVENTS=6`
- `BOT_RATE_LIMIT_WINDOW_SECONDS=30`
- `BOT_HTTP_RETRY_ATTEMPTS=2`
- `BOT_HTTP_RETRY_BACKOFF=0.7`

## Локальная проверка

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m pytest -q
```

## Деплой бота на VPS (Docker)

```powershell
powershell -ExecutionPolicy Bypass -File ".agent-remote/deploy-telegram-bot.ps1"
```

## Ветки (принятая схема)

- `main` — серверная/прод-ветка для развертывания.
- `local-helper` — вспомогательная ветка для локальных ПК-специфичных доработок.

## Примечание

Подробный журнал изменений по этапам и решениям ведется в:
- `Documentation/lightrag_guide.md`

