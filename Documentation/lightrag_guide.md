# LightRAG: Полное руководство

---

## Что такое LightRAG и чем он отличается от обычного RAG

**Обычный RAG** — это "поиск по кускам текста". Документ разбивается на чанки, каждый чанк превращается в вектор, при запросе ищутся похожие векторы. Работает, но плохо понимает _связи между понятиями_.

**LightRAG** добавляет поверх этого **граф знаний (Knowledge Graph)**. LLM сам извлекает из текста сущности (персоны, организации, концепции, методы) и связи между ними, строит граф, и при запросе ищет не только похожие чанки, но и _связанные узлы графа_.

```

---

## Лог работ агента

- 2026-04-21 18:58:50 — Запрос: "сначала сделай readme, потом проверь gitignore + lightrag_guide.md, и запушь в GitHub с разделением веток (серверная основная / локальная вспомогательная)". Выполнено: создан `README.md`, добавлен `.gitignore`, обновлен `Documentation/lightrag_guide.md`, инициализирован git, сделаны и запушены ветки `main` и `local-helper` в `https://github.com/alexklychnikov-ui/LightRAG`.
- 2026-04-21 19:15:38 — Запрос: проверить, проходит ли Q&A все fallback-режимы. Выполнено: исправлен `ask_with_fallback` в `telegram_bot/lightrag_client.py` — теперь ответ содержит фактически проверенные режимы; при слабом ответе во всех режимах возвращается последний режим + пометка, что все ответы слабые; добавлен unit-тест `test_ask_with_fallback_all_modes_weak`, общий прогон тестов: `41 passed`.
- 2026-04-21 19:22:43 — Запрос: включить ответ модели последним в цепочку Q&A. Выполнено: в `telegram_bot/handlers.py` обновлен парсер fallback-режимов, теперь по умолчанию цепочка `mix -> hybrid -> global -> naive` (даже если в env не указан `naive`); добавлены/обновлены тесты `tests/test_handlers_utils.py`, прогон тестов: `42 passed`, деплой `telegram-bot` на VPS выполнен.
- 2026-04-21 19:32:12 — Запрос: добавить работу с моделью вне RAG. Выполнено: добавлен прямой OpenAI fallback (`query_openai_general`) в `telegram_bot/lightrag_client.py`; в `telegram_bot/handlers.py` при слабом ответе всей RAG-цепочки выполняется финальный запрос к модели вне RAG и выводится `Источник ответа`; обновлен `README.md` (новые ENV: `BOT_ENABLE_OPENAI_FALLBACK`, `OPENAI_API_KEY`, `BOT_OPENAI_MODEL`, `OPENAI_API_BASE_URL`), на VPS включен `BOT_ENABLE_OPENAI_FALLBACK=true`, тесты `44 passed`, деплой выполнен.
- 2026-05-15 10:19:06 — Запрос: усилить парсинг URL из Telegram — обход внутренних ссылок того же сайта. Выполнено: в `telegram_bot/url_ingest.py` реализован BFS по страницам с тем же `netloc`, лимиты `BOT_URL_FOLLOW_MAX_PAGES`, `BOT_URL_FOLLOW_DEPTH`, `BOT_URL_FOLLOW_MAX_LINKS`; исправлен порт для `getaddrinfo` (80/443); тест `test_fetch_follows_same_site_link`, полный прогон `45 passed`; обновлён `README.md`.
- 2026-05-15 10:29:30 — Запрос: усилить «интеллектуальность» перевода на русский (не трогать команды ЯП, ближе к оригиналу по смыслу). Выполнено: в `telegram_bot/translation.py` добавлены детальные правила `TECHNICAL_TRANSLATION_RULES_RU` и эвристика `is_mostly_raw_code` вместо грубого отсечения по символам; `translate_to_russian` в `lightrag_client.py` использует новые инструкции; обновлены тесты, `46 passed`; правка `README.md`.
- 2026-05-15 10:37:44 — Запрос: контекст Q&A в Telegram, автоудаление после простоя (опционально). Выполнено: модуль `telegram_bot/qa_context.py` (история по `chat_id`, подмешивание в запрос, TTL `BOT_QA_SESSION_IDLE_MINUTES`, лимиты сообщений/символов), фоновый prune в `main.py`, `/forgetctx`, сброс при `/start`, тесты `tests/test_qa_context.py`, обновлены `README.md`, `domain.py`, `handlers.py`; полный прогон `50 passed`.
- 2026-05-20 — Запрос: веб-поиск в Q&A (этап 1 — абстракция). Промпт: исследование + план; этап 1 — модуль `telegram_bot/web_search.py` (`WebSearchResult`, провайдеры `tavily`/`ddgs`, `search_web`, дедуп URL, ENV-лимиты), зависимости `tavily-python`, `ddgs` в `requirements.txt`, тесты `tests/test_web_search.py`.
- 2026-05-20 — Проверка `TAVILY_API_KEY` в `/opt/LightRAG/.env`: ключ задан (`tvly-…`, len=58), `BOT_ENABLE_WEB_SEARCH=true`, live Tavily HTTP 200 (2 результата). В контейнере `lightrag-telegram-bot` переменная пока **не подхвачена** (контейнер 5 дней без recreate) — нужен `docker compose … up -d --force-recreate telegram-bot` после деплоя `web_search.py`.
- 2026-05-20 — Этап 2 веб-поиска Q&A: `telegram_bot/answer_completeness.py` (`assess_rag_answer`, `CompletenessVerdict`, fast-path для слабого RAG), `LightRAGClient.query_openai_json`; деплой с `--force-recreate` в `deploy-telegram-bot.ps1`. Агент пересоздаёт контейнеры сам при необходимости.
- 2026-05-20 — Этап 3 веб-поиска Q&A: `telegram_bot/web_answer_synthesis.py` (`synthesize_with_web`, `format_answer_with_references`, References только из результатов поиска, scrub чужих URL), `LightRAGClient.query_openai_chat`; тесты `tests/test_web_answer_synthesis.py`, деплой на VPS.
- 2026-05-20 — Этап 4 веб-поиска Q&A: интеграция в `handlers.py` — цепочка RAG → `assess_rag_answer` → Tavily `search_web` → `synthesize_with_web` → References; OpenAI fallback после веба; метрики `qa_web_*`; `qa_context.get_dialog_context_block`; деплой telegram-bot на VPS.
- 2026-05-20 — Code review web Q&A (субагент): исправлены WEB-01 (OpenAI не затирает web), WEB-02 (fast-path при judge off), WEB-03 (история без References), WEB-04/CLIP (judge по `effective_question` + `chat_context`), WEB-07/08/16, `BOT_OPENAI_TIMEOUT_SECONDS=45`; 81 passed; деплой telegram-bot.
- 2026-05-21 — Запрос: выбор reasoning-моделей OpenAI в Q&A, каталог с ценами при старте, default o4-mini. Выполнено: `telegram_bot/openai_models.py` (статический топ-5 + `GET /v1/models` при старте), inline `/omodel` + кнопки, `model=` в judge/синтез/fallback, `BOT_OPENAI_MODEL` default `o4-mini`; review-fix: longest-prefix match каталога, без `temperature` для o/gpt-5; 105 passed; деплой telegram-bot x2.
- 2026-05-30 — Промпт: «Q&A в Telegram как качественное резюме из БЗ (OV05 + LightRAG), точность важнее скорости». Выполнено: модуль `telegram_bot/deep_qa.py` — планировщик подзапросов (OpenAI JSON) → 3–8 запросов `ask_with_fallback` → синтез только из фрагментов БЗ; для `resume`/`document` отключены веб и OpenAI-fallback без RAG; `BOT_ENABLE_DEEP_QA`, `BOT_DEEP_QA_*`, `BOT_LIGHTRAG_TIMEOUT_SECONDS`; интеграция в `handlers.py`, статус, тесты `tests/test_deep_qa.py`; деплой telegram-bot на VPS.
- 2026-05-30 — Промпт: «всегда минимум 3 подзапроса (суть / детали / источники в БЗ)». Выполнено: `ensure_minimum_sub_queries`, `_triad_sub_query_templates`, `BOT_DEEP_QA_MIN_SUBQUERIES`; fallback и финализация плана всегда ≥3 запросов; тесты; деплой telegram-bot.
- 2026-06-10 — Промпт: миграция с умершего 193.168.196.12 на 45.144.28.49; восстановить alexklychnikov-ui/LightRAG и .env. На новом VPS обнаружен чужой docker-стек `OleksandrKucherenko/lightrag`; заменён на HKUDS+Postgres+telegram_bot overlay (scp). Private GitHub repo с сервера недоступен без deploy key. `.env` частично восстановлен; `OPENAI_API_KEY` OK; `TELEGRAM_BOT_TOKEN`/`TAVILY_API_KEY` — нужно вручную. Скрипты: `.agent-remote/restore-vps.sh`, `docker-compose.restore-vps.yml`.

---

## Git ветки для работы

- `main` — основная серверная ветка (все, что нужно для развертывания на VPS).
- `local-helper` — вспомогательная локальная ветка (ПК-специфичные и временные доработки).

Рекомендуемый поток:
1. Основные фичи и серверный деплой ведем через `main`.
2. Локальные эксперименты делаем в `local-helper`.
3. В `main` попадает только то, что реально нужно на сервере.

┌─────────────────────────────────────────────────────────────┐
│                      Обычный RAG                            │
│                                                             │
│  Документ → [Чанк 1] [Чанк 2] [Чанк 3]                     │
│                       ↓                                     │
│              Векторный поиск → Ответ                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                        LightRAG                             │
│                                                             │
│  Документ → [Чанк 1] [Чанк 2] [Чанк 3]                     │
│                  ↓ LLM извлекает связи ↓                    │
│                                                             │
│    [API] ──использует──► [Redis]                            │
│      │                       │                              │
│      └──▶ [LangChain] ◄──────┘                              │
│               │                                             │
│               └──▶ [RAG-пайплайн]                           │
│                                                             │
│         (Граф знаний)                                       │
│                  ↓ Гибридный поиск ↓                        │
│                       Ответ                                 │
└─────────────────────────────────────────────────────────────┘
```

### Почему это лучше

| Характеристика | Обычный RAG | GraphRAG (Microsoft) | LightRAG |
|---|---|---|---|
| Понимает связи | ✗ | ✓ | ✓ |
| Скорость индексации | Быстро | Медленно | **5x быстрее GraphRAG** |
| Стоимость токенов | Дёшево | Дорого | **27x дешевле GraphRAG** |
| Инкрементальное добавление | ✓ | ✗ (пересборка) | ✓ |
| Сложность установки | Легко | Средне | Легко |

---

## Архитектура хранилища

LightRAG хранит данные в трёх слоях одновременно:

```
┌────────────────────────────────────────────────────────┐
│                  LightRAG Storage                      │
│                                                        │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  KV Storage │  │Vector Storage│  │Graph Storage │  │
│  │ (метаданные │  │ (эмбеддинги  │  │ (граф сущно- │  │
│  │  чанков)    │  │  чанков)     │  │  стей)       │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │         Document Status Storage                  │  │
│  │    (PENDING / PROCESSING / PROCESSED / FAILED)   │  │
│  └─────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### Варианты бэкендов хранилища

| Слой | По умолчанию (JSON) | Для продакшна |
|---|---|---|
| KV | `JsonKVStorage` | PostgreSQL |
| Vector | `NanoVectorDB` | pgvector, Milvus, Chroma |
| Graph | `NetworkXStorage` (`.graphml` файл) | Neo4j, PostgreSQL |
| Doc Status | `JsonDocStatusStorage` | PostgreSQL |

> **Совет:** На VPS с небольшой нагрузкой JSON-бэкенды работают отлично. Переходи на PostgreSQL когда документов > 10 000 или нужна надёжность при перезапусках.

---

## Режимы запросов (Query Modes)

LightRAG поддерживает 5 режимов поиска. Выбираешь при каждом запросе:

| Режим | Что делает | Когда использовать |
|---|---|---|
| `naive` | Простой чанковый поиск, без графа | Быстрые фактические вопросы, тест |
| `local` | Поиск по локальному подграфу вокруг найденных сущностей | Вопросы о конкретном объекте/человеке |
| `global` | Обход всего графа знаний | Обзорные вопросы: "Какие темы в базе?" |
| `hybrid` | `local` + `global` | Хорошая точность для большинства задач |
| `mix` | `hybrid` + векторный поиск по чанкам | **Рекомендован для продакшна** |

```bash
# Пример запроса с режимом mix
curl -X POST "http://localhost:9621/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Как работает индексация?", "mode": "mix"}'
```

---

## Конфигурация: файл .env с объяснением каждого параметра

```env
# ================================================================
# LLM — языковая модель для извлечения сущностей и генерации ответов
# ================================================================
LLM_BINDING=ollama          # ollama | openai | azure | anthropic | lollms
LLM_MODEL=qwen2.5:32b       # ВАЖНО: минимум 32B для качественного графа!
                             # Маленькие модели (7B, 14B) плохо извлекают связи
LLM_BINDING_HOST=http://localhost:11434   # адрес Ollama или OpenAI-совместимого API
LLM_BINDING_API_KEY=        # для OpenAI/Azure/Anthropic — ключ API

# ================================================================
# Эмбеддинги — модель для векторизации чанков
# ================================================================
EMBEDDING_BINDING=ollama
EMBEDDING_MODEL=bge-m3:latest     # Хорошие варианты: bge-m3, nomic-embed-text
EMBEDDING_DIM=1024                # Размерность: bge-m3=1024, nomic=768, text-ada=1536
EMBEDDING_BINDING_HOST=http://localhost:11434

# ================================================================
# Сервер
# ================================================================
PORT=9621
HOST=0.0.0.0
CORS_ORIGINS=*              # Разрешить запросы с любых доменов

# ================================================================
# Параметры RAG — влияют на качество и скорость
# ================================================================
CHUNK_SIZE=1200             # Размер чанка в токенах. 1200 — оптимум.
                             # Меньше = больше чанков = дороже индексация
                             # Больше = теряется детализация
CHUNK_OVERLAP_SIZE=100      # Перекрытие между чанками — чтобы не терять контекст на границах
MAX_ASYNC=4                 # Параллельных LLM-запросов при индексации
                             # Увеличь если Ollama справляется, уменьши при ошибках OOM
TOP_K=40                    # Сколько результатов возвращать при поиске
COSINE_THRESHOLD=0.2        # Минимальный порог сходства (0.0–1.0)
                             # Выше = строже фильтрация = меньше результатов

# ================================================================
# Язык и сущности
# ================================================================
SUMMARY_LANGUAGE=Russian    # Язык саммари и описаний сущностей в графе
                             # Если документы на русском — обязательно ставь Russian

# Типы сущностей для извлечения в граф. Настрой под свою предметную область:
# Для IT-документации:
ENTITY_TYPES=Person,Organization,Location,Event,Concept,Method,Technology,API,Module,Database,Service

# ================================================================
# Кэширование — экономит токены при повторных запросах
# ================================================================
LLM_CACHE_ENABLED=true
LLM_CACHE_FOR_EXTRACT=true  # Кэшировать извлечение сущностей

# ================================================================
# Хранилище — PostgreSQL для продакшна (раскомментируй если нужно)
# ================================================================
# POSTGRES_URL=postgresql://lightrag:password@localhost:5432/lightrag_db
```

---

## Способы пополнения базы без веб-интерфейса

### Способ 1: curl — самый простой

```bash
# --- Добавить текст напрямую ---
curl -X POST "http://YOUR_VPS:9621/documents/text" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Текст для добавления в базу знаний",
    "description": "Необязательное описание"
  }'

# --- Загрузить файл (txt, pdf, md, docx) ---
curl -X POST "http://YOUR_VPS:9621/documents/file" \
  -F "file=@/home/user/document.pdf" \
  -F "description=Мой документ"

# --- Пакетная загрузка нескольких файлов ---
curl -X POST "http://YOUR_VPS:9621/documents/batch" \
  -F "files=@/home/user/doc1.txt" \
  -F "files=@/home/user/doc2.md" \
  -F "files=@/home/user/doc3.pdf"

# --- Сканировать папку inputs/ на новые файлы ---
# (положи файлы в папку inputs/ LightRAG, затем вызови сканирование)
curl -X POST "http://YOUR_VPS:9621/documents/scan" --max-time 1800

# --- Проверить статус документов ---
curl "http://YOUR_VPS:9621/documents"

# --- Статус пайплайна (идёт ли обработка прямо сейчас?) ---
curl "http://YOUR_VPS:9621/documents/pipeline_status"
```

### Способ 2: Python-скрипт для массовой загрузки

```python
#!/usr/bin/env python3
"""
Скрипт для загрузки документов в LightRAG.
Запуск: python upload_to_lightrag.py ./my_docs_folder
"""
import os
import sys
import requests

LIGHTRAG_URL = "http://YOUR_VPS:9621"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".rst"}


def upload_text(text: str, description: str = "") -> dict:
    """Добавить текст напрямую."""
    resp = requests.post(
        f"{LIGHTRAG_URL}/documents/text",
        json={"text": text, "description": description},
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()


def upload_file(file_path: str) -> dict:
    """Загрузить файл."""
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{LIGHTRAG_URL}/documents/file",
            files={"file": (filename, f)},
            data={"description": filename},
            timeout=120
        )
    resp.raise_for_status()
    return resp.json()


def upload_folder(folder_path: str):
    """Загрузить все поддерживаемые файлы из папки."""
    files = [
        f for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]
    print(f"Найдено файлов: {len(files)}")
    
    for i, filename in enumerate(files, 1):
        path = os.path.join(folder_path, filename)
        try:
            result = upload_file(path)
            print(f"[{i}/{len(files)}] ✓ {filename}")
        except Exception as e:
            print(f"[{i}/{len(files)}] ✗ {filename}: {e}")


def check_status():
    """Показать статусы документов."""
    resp = requests.get(f"{LIGHTRAG_URL}/documents", timeout=30)
    docs = resp.json()
    for doc in docs.get("statuses", {}).values():
        print(f"  {doc.get('status', '?'):12} — {doc.get('file_path', 'unknown')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python upload.py <папка>          — загрузить всю папку")
        print("  python upload.py <файл.txt>       — загрузить один файл")
        print("  python upload.py --status         — показать статусы")
        sys.exit(1)
    
    arg = sys.argv[1]
    if arg == "--status":
        check_status()
    elif os.path.isdir(arg):
        upload_folder(arg)
    elif os.path.isfile(arg):
        upload_file(arg)
        print(f"✓ Загружено: {arg}")
```

### Способ 3: Папка inputs/ + автоматическое сканирование

Это самый ленивый способ. На VPS в папке с LightRAG есть директория `inputs/`:

```bash
# Копируешь файлы туда
cp /tmp/my_notes.txt /opt/lightrag/inputs/
cp /tmp/docs/*.pdf   /opt/lightrag/inputs/

# Запускаешь сканирование — LightRAG сам всё найдёт и обработает
curl -X POST "http://localhost:9621/documents/scan"
```

Можно добавить в cron для автоматической загрузки каждую ночь:

```cron
# Каждую ночь в 3:00 сканировать папку inputs/
0 3 * * * curl -s -X POST http://localhost:9621/documents/scan
```

---

## Интеграция с Telegram

### Архитектура

```
Пользователь пишет в Telegram
         │
         ▼
   [Telegram Bot]  ← python-telegram-bot
         │
    ┌────┴──────────────────────┐
    │  Вопрос?                  │  Файл?
    ▼                           ▼
POST /query               POST /documents/file
    │                           │
    └────────────┬──────────────┘
                 ▼
         [LightRAG API :9621]
                 │
         ┌───────┴────────┐
         │  Граф знаний   │
         │  + Векторы     │
         └───────┬────────┘
                 ▼
           Ответ LLM
                 │
                 ▼
    Пользователь получает ответ
```

### Этап 0: контракт интеграции Telegram-бота с LightRAG

Цель: зафиксировать интерфейс и границы модулей до реализации кода.

**Границы системы**
- Telegram-бот отвечает только за UX, FSM и маршрутизацию.
- Вся работа с базой знаний идёт через LightRAG API (`/documents/*`, `/query`).
- Логика индексации не дублируется в боте, бот только вызывает существующий pipeline.

**Режимы постоянного меню**
- `Пополнить БЗ`
  - Вход: любой текст, любой файл, URL.
  - Выход: статус ingest (`accepted`/`failed`) + краткая причина.
- `Задать вопрос`
  - Вход: текст вопроса.
  - Выход: ответ ИИ на основе LightRAG retrieval.
- `Статус`
  - Вход: команда из меню.
  - Выход: `health`, `pipeline_status`, краткая сводка по документам.

**Контракт Bot Service Layer**
- `ingest_text(text: str, source: str = "telegram") -> IngestResult`
- `ingest_file(file_meta, file_bytes) -> IngestResult`
- `ingest_url(url: str) -> IngestResult`
- `ask(question: str, mode: str = "mix") -> AnswerResult`
- `get_status() -> StatusResult`

**Контракт данных (минимум)**
- `IngestResult`: `ok: bool`, `job_id: str|None`, `message: str`, `source_type: text|file|url`
- `AnswerResult`: `ok: bool`, `answer: str`, `mode_used: str`, `context_found: bool`
- `StatusResult`: `ok: bool`, `health: str`, `pipeline_state: str`, `documents_total: int`

**Нефункциональные требования**
- Rate-limit на пользователя/чат.
- Таймауты и retry на запросах к LightRAG.
- Запрет на hardcode ключей (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_CHATID` только через `.env`).
- Ошибки наружу в безопасном и коротком виде.

### Поэтапный TODO реализации (зафиксирован)

- [x] Этап 0: архитектура, контракты, режимы меню, формат логирования.
- [x] Этап 1: кнопка `Menu` + inline-меню + FSM (`INGEST_MODE`, `QA_MODE`) + docker deployment на сервере.
- [x] Этап 2: ingest текста.
- [x] Этап 3: ingest файлов.
- [x] Этап 4: ingest URL (парсинг + выделение значимого контента).
- [x] Этап 5: Q&A через LightRAG retrieval.
- [x] Этап 6: надежность (rate-limit, retry, централизованный error handler).
- [x] Этап 7: E2E, тесты, code review subagent, цикл до полного green.

### Версионный лог работ по Telegram ↔ LightRAG

- `2026-04-21 15:25:18` — Промпт: "Старт этап 0". Сделано: зафиксирован контракт интеграции, режимы меню, API-границы, TODO по этапам и критерии для следующей реализации.
- `2026-04-21 15:32:28` — Промпт: "Старт этап 1" + уточнение "бот на сервере в Docker". Сделано: добавлен каркас aiogram (menu/inline/FSM), подготовлены `telegram_bot/Dockerfile`, compose overlay `.agent-remote/docker-compose.telegram-bot.yml`, скрипт удаленного деплоя `.agent-remote/deploy-telegram-bot.ps1`.
- `2026-04-21 15:36:48` — Code review этапа 1: исправлены риски деплоя/рантайма (`scp` sync без wildcard, неблокирующий health-check через `asyncio.to_thread`, валидация `TELEGRAM_BOT_CHATID`, фиксация версий зависимостей).
- `2026-04-21 15:40:00` — Деплой этапа 1 на VPS: bot-container собран и поднят через compose overlay, логи polling без ошибок; повторный subagent-review: блокеров для stage 1 нет.
- `2026-04-21 15:43:18` — Старт этапа 2: реализован ingest текста в режиме `Пополнить БЗ` (`/documents/text`), добавлена валидация входа и unit-тесты клиента LightRAG.
- `2026-04-21 15:46:26` — Фиксы после code-review этапа 2: ingest считает успехом любой `2xx`, возвращает body ошибки, лимит текста синхронизирован с Telegram (4096), расширены тесты (`202`, `RequestException`, проверка payload/url/timeout), добавлен `pytest.ini`.
- `2026-04-21 15:47:28` — Этап 2 завершен: тесты (`unittest` + `pytest`) green, контейнер на VPS перезапущен, финальный subagent-review: блокеров нет.
- `2026-04-21 16:10:05` — Hotfix авторизации ingest: добавлен `LIGHTRAG_API_KEY` -> заголовок `X-API-Key` в клиенте бота (health/ingest), обновлены unit-тесты и выполнен redeploy контейнера на VPS.
- `2026-04-21 16:16:54` — Устранение повторного `401`: принудительная синхронизация `telegram_bot/` на VPS (до этого в контейнере оставался старый код), повторная сборка контейнера, проверка probe-запросом к `/documents/text` с `X-API-Key` (HTTP 200). Текст подсказки ingest изменен на "Отправь текст.".
- `2026-04-21 16:27:28` — Этап 3 завершен: добавлен ingest файлов в Telegram-режиме (`document`), реализована совместимость endpoint-ов (`/documents/upload` с fallback на `/documents/file`), санитизация ошибок для пользователя, обработка ошибок download/лимита размера, тесты green (`unittest` + `pytest`), redeploy на VPS, probe upload `HTTP 200`, финальный subagent-review без блокеров.
- `2026-04-21 16:38:27` — Улучшение UX ingest: добавлен трекинг `track_id` и авто-уведомления в Telegram о ходе обработки (`обрабатывается` -> `обработан/ошибка`), fallback-логика статуса по `status_summary`, тесты расширены и green, контейнер на VPS пересобран.
- `2026-04-21 17:01:03` — Этап 4 завершен: добавлен ingest URL (fetch+extract значимого контента), SSRF-блокировка приватных/локальных адресов и запрет редиректов, ограничение размера загружаемой страницы, устойчивый трекинг статусов, тесты green (`unittest` + `pytest`), redeploy на VPS, финальный subagent-review без блокеров.
- `2026-04-21 17:13:44` — Добавлен авто-перевод на русский (`BOT_TRANSLATE_TO_RU=true`) для ingest текста/URL и текстовых файлов; перевод выполняется перед записью в LightRAG, при ошибке перевода работает fallback на оригинал; включена переменная в `/opt/LightRAG/.env`, тесты green, контейнер бота пересобран на VPS.
- `2026-04-21 17:15:51` — UX-доработка: бот теперь явно помечает режим сохранения после ingest — `Режим: перевод` или `Режим: оригинал` для текста/ссылок/файлов; деплой выполнен на VPS.
- `2026-04-21 17:29:16` — Этап 5 завершен: реализован режим `Задать вопрос` через LightRAG query, добавлен fallback режимов поиска (`mix -> hybrid -> global`), авто-перевод ответа на RU при включенном флаге, тесты расширены и green, контейнер бота пересобран на VPS, повторный subagent-review без блокеров.
- `2026-04-21 17:36:31` — Этап 6 завершен: добавлены rate-limit на чат, runtime-метрики бота (включая статус-сводку в режиме `Статус`), централизованный handler необработанных ошибок, retry-политика HTTP (с учетом `Retry-After` для 429), безопасное отключение retry для ingest POST (во избежание дублей), тесты расширены и green, деплой на VPS выполнен, финальный subagent-review без блокеров.
- `2026-04-21 17:44:51` — Этап 7 завершен: выполнен финальный E2E-прогон (text/file ingest, track_status, query), устранен блокер длинных Q&A-ответов (chunking под лимит Telegram), повторные тесты green, деплой на VPS выполнен, финальный subagent-review без блокеров.
- `2026-04-21 17:49:03` — Hotfix авто-перевода URL/техтекста: устранена ложная блокировка перевода из-за `https://` в контенте, усилен prompt для технического перевода (с сохранением команд/нод/API/параметров), тесты green, контейнер бота пересобран на VPS.
- `2026-04-21 18:29:35` — Hotfix Q&A usability: fallback теперь срабатывает не только по ошибке, но и по слабому ответу `mix`; добавлен rewrite популярных вопросов профиля; добавлен удобный выбор режима Q&A через кнопки и inline-синтаксис `режим:<mode> | вопрос`; деплой на VPS выполнен.

### Полный код бота

```python
#!/usr/bin/env python3
"""
Telegram-бот для LightRAG.
pip install python-telegram-bot requests
"""
import os
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)

LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://YOUR_VPS:9621")
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
QUERY_MODE   = os.getenv("QUERY_MODE", "mix")   # mix | hybrid | local | global | naive
# Если хочешь, чтобы бот отвечал только определённым пользователям:
ALLOWED_USERS = set()   # например {123456789, 987654321}, пусто = все


def ask_lightrag(question: str) -> str:
    try:
        resp = requests.post(
            f"{LIGHTRAG_URL}/query",
            json={"query": question, "mode": QUERY_MODE},
            timeout=120
        )
        data = resp.json()
        return data.get("response") or "Ответ не получен."
    except requests.Timeout:
        return "⏱ LightRAG не ответил за 2 минуты. Попробуй ещё раз."
    except Exception as e:
        return f"Ошибка: {e}"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот с базой знаний на LightRAG.\n\n"
        "• Просто напиши вопрос — отвечу из базы\n"
        "• /add <текст> — добавить текст в базу\n"
        "• /status — статус документов\n"
        "• Отправь файл — добавлю в базу"
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /add <текст> — добавить текст в базу."""
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Использование: /add <текст для добавления>")
        return

    await update.message.reply_text("⏳ Добавляю в базу знаний...")
    try:
        resp = requests.post(
            f"{LIGHTRAG_URL}/documents/text",
            json={"text": text},
            timeout=60
        )
        if resp.status_code == 200:
            await update.message.reply_text("✅ Текст принят, идёт обработка.")
        else:
            await update.message.reply_text(f"Ошибка: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status — показать статус документов."""
    try:
        resp = requests.get(f"{LIGHTRAG_URL}/documents", timeout=30)
        docs = resp.json()
        statuses = docs.get("statuses", {})
        if not statuses:
            await update.message.reply_text("База знаний пуста.")
            return

        lines = ["📚 Документы в базе:\n"]
        counts = {}
        for doc in statuses.values():
            status = doc.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1

        for status, count in counts.items():
            emoji = {"PROCESSED": "✅", "PROCESSING": "⏳", "FAILED": "❌", "PENDING": "🕐"}.get(status, "❓")
            lines.append(f"{emoji} {status}: {count} документов")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового вопроса."""
    if ALLOWED_USERS and update.effective_user.id not in ALLOWED_USERS:
        return

    question = update.message.text
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    answer = ask_lightrag(question)
    # Telegram ограничивает сообщение 4096 символами
    if len(answer) > 4000:
        answer = answer[:4000] + "...\n\n[Ответ обрезан]"

    await update.message.reply_text(answer)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принять файл и добавить в LightRAG."""
    doc = update.message.document
    allowed_types = {
        "text/plain", "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }

    if doc.mime_type not in allowed_types:
        await update.message.reply_text(
            f"Поддерживаю: .txt, .md, .pdf, .docx\nПолучил: {doc.mime_type}"
        )
        return

    await update.message.reply_text(f"⏳ Загружаю {doc.file_name}...")
    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()

    try:
        resp = requests.post(
            f"{LIGHTRAG_URL}/documents/file",
            files={"file": (doc.file_name, bytes(file_bytes))},
            data={"description": doc.file_name},
            timeout=120
        )
        if resp.status_code == 200:
            await update.message.reply_text(
                f"✅ {doc.file_name} принят. Обработка займёт несколько минут."
            )
        else:
            await update.message.reply_text(f"Ошибка загрузки: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
```

### Запуск на VPS как сервис

```bash
# Создаём окружение
python3 -m venv /opt/lightrag-bot/venv
/opt/lightrag-bot/venv/bin/pip install python-telegram-bot requests

# Кладём bot.py в /opt/lightrag-bot/bot.py

# Создаём systemd-сервис
cat > /etc/systemd/system/lightrag-bot.service << 'EOF'
[Unit]
Description=LightRAG Telegram Bot
After=network.target

[Service]
WorkingDirectory=/opt/lightrag-bot
ExecStart=/opt/lightrag-bot/venv/bin/python bot.py
Environment=BOT_TOKEN=123456:YOUR_BOT_TOKEN_HERE
Environment=LIGHTRAG_URL=http://localhost:9621
Environment=QUERY_MODE=mix
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lightrag-bot
systemctl start lightrag-bot
systemctl status lightrag-bot
```

---

## Интеграция с Cursor IDE через MCP

### Архитектура

```
Cursor IDE (Agent / Composer)
         │
         │  MCP Protocol (stdio)
         ▼
  [lightrag_mcp_server.py]   ← кастомный MCP-сервер
         │
         │  HTTP REST
         ▼
  [LightRAG API :9621]
         │
    ┌────┴────────┐
    │ Граф знаний │
    │ + Векторы   │
    └─────────────┘
```

### Шаг 1: Установить MCP SDK

```bash
pip install mcp
```

### Шаг 2: Создать MCP-сервер

```python
# lightrag_mcp_server.py
"""
MCP-сервер для подключения LightRAG к Cursor IDE.
Cursor будет использовать его как инструмент для поиска в базе знаний.
"""
import asyncio
import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

LIGHTRAG_URL = "http://YOUR_VPS_IP:9621"

server = Server("lightrag-knowledge-base")


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="search_knowledge_base",
            description=(
                "Поиск информации в персональной базе знаний LightRAG. "
                "Используй для поиска документации, заметок, архитектурных решений, "
                "кодовых паттернов и любой информации из загруженных документов."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Вопрос или тема для поиска"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["naive", "local", "global", "hybrid", "mix"],
                        "default": "mix",
                        "description": "Режим поиска. mix — рекомендован для большинства запросов"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="add_to_knowledge_base",
            description=(
                "Добавить текст или документ в базу знаний LightRAG. "
                "Используй для сохранения важных находок, решений, документации."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Текст для добавления в базу знаний"
                    },
                    "description": {
                        "type": "string",
                        "description": "Краткое описание документа (необязательно)"
                    }
                },
                "required": ["text"]
            }
        ),
        types.Tool(
            name="knowledge_base_status",
            description="Проверить статус и здоровье LightRAG сервера.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "search_knowledge_base":
        try:
            resp = requests.post(
                f"{LIGHTRAG_URL}/query",
                json={
                    "query": arguments["query"],
                    "mode": arguments.get("mode", "mix")
                },
                timeout=120
            )
            result = resp.json().get("response", "Нет ответа от базы знаний.")
            return [types.TextContent(type="text", text=result)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Ошибка поиска: {e}")]

    elif name == "add_to_knowledge_base":
        try:
            resp = requests.post(
                f"{LIGHTRAG_URL}/documents/text",
                json={
                    "text": arguments["text"],
                    "description": arguments.get("description", "")
                },
                timeout=60
            )
            status = "✅ Добавлено успешно" if resp.status_code == 200 else f"Ошибка: {resp.status_code}"
            return [types.TextContent(type="text", text=status)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Ошибка: {e}")]

    elif name == "knowledge_base_status":
        try:
            resp = requests.get(f"{LIGHTRAG_URL}/health", timeout=10)
            return [types.TextContent(type="text", text=str(resp.json()))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"LightRAG недоступен: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
```

### Шаг 3: Подключить к Cursor

Открыть Cursor → `Ctrl+Shift+J` (Settings) → раздел **MCP** → **Add MCP Server**:

```json
{
  "mcpServers": {
    "lightrag": {
      "command": "python",
      "args": ["C:/path/to/lightrag_mcp_server.py"]
    }
  }
}
```

Или если на Windows с WSL:
```json
{
  "mcpServers": {
    "lightrag": {
      "command": "wsl",
      "args": ["python3", "/home/user/lightrag_mcp_server.py"]
    }
  }
}
```

### Шаг 4: Использование в Cursor

После подключения в Composer/Agent появятся инструменты. Можно писать напрямую:

```
@lightrag Найди в базе знаний, как я настраивал индексы в AX 2012
```

```
@lightrag Добавь в базу знаний следующее решение: [текст]
```

Или агент сам будет обращаться к базе знаний при необходимости.

---

## Интеграция с n8n (автоматизация)

### Базовый workflow: загрузка документов

```
┌──────────────────────────────────────────────────────────┐
│                    n8n Workflow                           │
│                                                          │
│  [Trigger]  →  [HTTP Request: POST /documents/text]      │
│                                                          │
│  Варианты триггера:                                      │
│  • Schedule (каждую ночь)                                │
│  • Webhook (от другого сервиса)                          │
│  • Gmail Trigger (новое письмо)                          │
│  • Telegram Trigger (сообщение в канал)                  │
│  • RSS Feed Trigger (новые статьи)                       │
└──────────────────────────────────────────────────────────┘
```

### Настройка HTTP Request ноды в n8n

**Method:** POST  
**URL:** `http://YOUR_VPS:9621/documents/text`  
**Headers:**
```
Content-Type: application/json
```
**Body (JSON):**
```json
{
  "text": "={{ $json.content }}",
  "description": "={{ $json.title || 'Без названия' }}"
}
```

### Сценарии автоматизации

**1. Gmail → LightRAG**
```
Gmail Trigger (новые письма)
  → Extract text from email body
  → HTTP POST /documents/text
  → (опционально) Send Telegram notification "Добавлено в базу"
```

**2. Telegram-канал → LightRAG**
```
Telegram Trigger (новый пост в канале)
  → HTTP POST /documents/text с текстом поста
  → Автоматическая база знаний из канала
```

**2a. Telegram-бот (aiogram) → LightRAG**
```
Пользователь/канал в Telegram
  → Bot Menu (постоянная кнопка) -> inline-режимы:
      [Пополнить БЗ] [Задать вопрос] [Статус]
  → Bot Service Layer (ingest/query)
      ingest(text|file|url) -> LightRAG /documents/*
      ask(question) -> LightRAG /query (mode=mix, fallback=hybrid/global)
  → Ответ пользователю в Telegram
```

**3. Еженедельный дайджест → LightRAG**
```
Schedule (каждый понедельник)
  → HTTP GET (парсинг нужного сайта/API)
  → HTTP POST /documents/text
  → База знаний всегда актуальна
```

**4. GitHub → LightRAG (документация из PR)**
```
Webhook (GitHub PR merged)
  → Get PR description + diff
  → HTTP POST /documents/text
  → Cursor всегда знает об изменениях
```

### Пример: загрузка через Webhook (внешний триггер)

```bash
# Отправить данные в n8n Webhook → n8n передаст в LightRAG
curl -X POST "http://YOUR_N8N:5678/webhook/lightrag-add" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Решение проблемы с индексами AX",
    "content": "Текст документа или заметки..."
  }'
```

---

## Диагностика и полезные команды

```bash
# Проверить что сервер живой
curl http://localhost:9621/health

# Список документов и их статусы
curl http://localhost:9621/documents | python3 -m json.tool

# Идёт ли обработка прямо сейчас?
curl http://localhost:9621/documents/pipeline_status

# Тестовый запрос (проверить что граф работает)
curl -X POST http://localhost:9621/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Что есть в моей базе знаний?", "mode": "global"}'

# Потоковый ответ (streaming)
curl -X POST http://localhost:9621/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Расскажи о содержимом базы", "mode": "mix"}'

# Удалить все документы (ОСТОРОЖНО! Необратимо)
curl -X DELETE http://localhost:9621/documents
```

---

---

## Обновление документов: важные особенности

> **Коротко:** LightRAG не умеет «обновлять» документы — только добавлять новые. Повторная загрузка изменённого документа загрязняет граф устаревшими данными. Решение — сначала DELETE, потом POST.

### Что происходит при повторной загрузке

```
Документ v1 отправлен → обработан → в хранилище:
  KV:     чанки v1 с их хешами
  Vector: эмбеддинги чанков v1
  Graph:  сущности и связи из v1

Документ v2 отправлен (тот же файл, но с правками):
  ┌─────────────────────────────────────────────────┐
  │  LightRAG смотрит на ID документа / хеш файла  │
  └─────────────────────────────────────────────────┘
         │                        │
    Если ID совпал          Если ID новый
    (например, то же        (например, разный
    имя файла через /scan)  текст через /text)
         │                        │
         ▼                        ▼
   ПРОПУСКАЕТ                ДОБАВЛЯЕТ поверх:
   (не обрабатывает          - новые чанки → в Vector
   повторно)                 - новые сущности → в Graph
                             - старые сущности ОСТАЮТСЯ
```

### Два сценария

**Сценарий А: загрузка через `/documents/file` или `/scan`**

LightRAG вычисляет хеш файла. Если файл изменился — хеш другой — документ считается новым и добавляется **поверх** старого. Старые чанки и сущности при этом **не удаляются**.

Результат в графе: будут висеть обе версии сущностей и связей одновременно. При запросе модель получит противоречивые данные.

**Сценарий Б: загрузка через `/documents/text` (сырой текст)**

Проверки на дубликаты нет вообще. Каждый вызов — новый документ. Отправил дважды — получил два независимых набора чанков и сущностей в графе.

### Правильный способ обновить документ

Единственный надёжный алгоритм: **удалить старый → добавить новый**.

```bash
# 1. Найти ID документа
curl http://localhost:9621/documents
# В ответе:
# { "statuses": { "doc-abc123": { "file_path": "my_doc.pdf", ... } } }

# 2. Удалить конкретный документ по ID
curl -X DELETE "http://localhost:9621/documents/doc-abc123"

# 3. Загрузить новую версию
curl -X POST "http://localhost:9621/documents/file" \
  -F "file=@my_doc_v2.pdf"
```

Или Python-функция для удобного переиспользования:

```python
import requests

LIGHTRAG_URL = "http://YOUR_VPS:9621"

def get_doc_id_by_name(filename: str) -> str | None:
    """Найти ID документа по имени файла."""
    resp = requests.get(f"{LIGHTRAG_URL}/documents", timeout=30)
    statuses = resp.json().get("statuses", {})
    for doc_id, info in statuses.items():
        if filename in info.get("file_path", ""):
            return doc_id
    return None

def replace_document(filename: str, new_file_path: str):
    """Заменить документ: удалить старый, загрузить новый."""
    doc_id = get_doc_id_by_name(filename)
    if doc_id:
        requests.delete(f"{LIGHTRAG_URL}/documents/{doc_id}")
        print(f"Удалён старый документ: {doc_id}")
    else:
        print(f"Документ {filename} не найден в базе, просто добавляю новый")

    with open(new_file_path, "rb") as f:
        requests.post(
            f"{LIGHTRAG_URL}/documents/file",
            files={"file": f},
            timeout=120
        )
    print(f"Загружена новая версия: {new_file_path}")

# Использование
replace_document("my_doc.pdf", "./my_doc_v2.pdf")
```

### Проверить наличие дубликатов

```bash
# Посмотреть все документы — ищи одинаковые file_path с разными ID
curl http://localhost:9621/documents | python3 -m json.tool | grep file_path
```

Если видишь один и тот же файл дважды с разными ID — это дубликат, его нужно почистить через DELETE.

---

## Советы по оптимизации

### Модель

- **Минимум 32B** для качественного извлечения сущностей. `qwen2.5:32b` — отличный выбор для Ollama.
- Мелкие модели (7B, 14B) будут строить плохой граф: пропускать связи, галлюцинировать сущности.
- Для эмбеддингов можно использовать лёгкую модель: `bge-m3` (567M параметров).

### Чанки и параметры

| Параметр | Рекомендация |
|---|---|
| `CHUNK_SIZE` | 1200 — оптимум для большинства задач |
| `CHUNK_OVERLAP` | 100–150 — не терять контекст на границах |
| `TOP_K` | 40 для общих вопросов, 60–80 для детальных |
| `COSINE_THRESHOLD` | 0.2 — стандарт. Повысь до 0.3–0.4 для меньшего шума |

### Язык документов

Если документы на **русском** — обязательно:
```env
SUMMARY_LANGUAGE=Russian
```
Иначе граф будет строиться на английском, а качество поиска на русских запросах упадёт.

### Entity Types под IT-разработку

```env
ENTITY_TYPES=Person,Organization,Technology,API,Module,Database,Service,Method,Concept,Error,Solution,Framework
```

### Кэширование

```env
LLM_CACHE_ENABLED=true
LLM_CACHE_FOR_EXTRACT=true
```

Особенно важно при повторном добавлении похожих документов — не будет лишних LLM-вызовов.

### PostgreSQL для продакшна

При большом объёме (>5000 документов) JSON-файлы тормозят. Переключайся:

```env
POSTGRES_URL=postgresql://lightrag:password@localhost:5432/lightrag_db
```

```bash
# Создать базу
createdb lightrag_db
createuser lightrag -P
```

---

## Шпаргалка: быстрый старт интеграций

```
┌─────────────────────────────────────────────────────────────────┐
│                    LightRAG на VPS :9621                        │
│                                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────────┐    │
│  │ Telegram    │   │ Cursor IDE   │   │ n8n               │    │
│  │ Bot         │   │ (MCP)        │   │ (автоматизация)   │    │
│  │             │   │              │   │                   │    │
│  │ /query      │   │ search_kb    │   │ HTTP Request      │    │
│  │ /documents  │   │ add_to_kb    │   │ POST /documents   │    │
│  └──────┬──────┘   └──────┬───────┘   └─────────┬─────────┘    │
│         │                 │                     │              │
│         └─────────────────┼─────────────────────┘              │
│                           │                                     │
│                    REST API (HTTP)                              │
│                    POST /query                                  │
│                    POST /documents/text                         │
│                    POST /documents/file                         │
│                    GET  /documents                              │
└─────────────────────────────────────────────────────────────────┘
```
