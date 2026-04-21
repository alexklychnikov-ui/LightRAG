# LightRAG MCP — Памятка

## 1) Что уже настроено

- LightRAG API: `https://lightrag.alexklyvibe.ru`
- OAuth перед доменом: `oauth2-proxy` (Google)
- Storage профиль:
  - `PGKVStorage`
  - `PGDocStatusStorage`
  - `PGVectorStorage`
  - `NetworkXStorage` для графа
- PostgreSQL контейнер: `pgvector/pgvector:pg16`
- Версия LightRAG: `1.4.14` (runtime)

## 2) Ключевые файлы

- Локально (проект):
  - `.cursor/mcp.json`
  - `.cursor/rules/lightrag-auto-lookup.mdc`
  - `.cursor/rules/lightrag-shortcuts.mdc`
  - `.cursor/skills/lightrag-chatops/SKILL.md`
  - `.cursor/skills/lightrag-ingestion-operator/SKILL.md`
  - `.cursor/skills/lightrag-research-loop/SKILL.md`
  - `lightrag_mcp_server.py`

- Глобально (Cursor user):
  - `C:/Users/User/.cursor/mcp.json`

- На сервере:
  - `/opt/LightRAG/lightrag_mcp_server.py`
  - `/opt/lightrag-mcp-venv/`
  - `/opt/LightRAG/.env`
  - `/opt/LightRAG/docker-compose.yml`

## 3) MCP сервер (как запускается)

- Cursor запускает MCP через `ssh` на VPS.
- На VPS стартует:
  - `/opt/lightrag-mcp-venv/bin/python /opt/LightRAG/lightrag_mcp_server.py`
- URL API берется как `http://127.0.0.1:9621`
- `LIGHTRAG_API_KEY` берется из `/opt/LightRAG/.env`

## 4) Инструменты MCP

- `search_knowledge_base`
- `add_text_to_knowledge_base`
- `upsert_text_to_knowledge_base`
- `add_file_to_knowledge_base`
- `scan_inputs_folder`
- `knowledge_base_status`
- `list_documents`

## 5) Команды в чате (полные)

- `@lightrag Найди <запрос>`
- `@lightrag Добавь в базу знаний <текст>`
- `@lightrag Добавь в базу знаний @<локальный_файл>` (upsert: удалить старую версию + добавить новую)
- `@lightrag Добавь в базу знаний файл /opt/...` (upsert по имени файла: удалить старую версию + добавить новую)

## 6) Команды в чате (короткие алиасы)

- `@lightrag ? <запрос>` -> поиск в БЗ
- `@lightrag + <текст>` -> добавить текст
- `@lightrag + @<локальный_файл>` -> прочитать локальный файл и сохранить через upsert (replace_existing=true)
- `@lightrag + файл /opt/...` -> сохранить файл по абсолютному пути на VPS через upsert (replace_existing=true)
- `@lightrag scan` -> запуск `/documents/scan`
- `@lightrag status` -> health + pipeline status
- `@lightrag docs` -> список документов

## 6.1) Горячие клавиши в Cursor (чат)

- Основной рабочий вариант: AutoHotkey v2 + скрипт `.agent-remote/cursor-lightrag-hotkeys.ahk`
- Горячие клавиши:
  - `F6` -> вставить `@lightrag ? `
  - `F7` -> вставить `@lightrag + `
  - `F8` -> вставить `@lightrag status`

Почему через AHK:
- В текущей сборке Cursor отсутствуют часть chat-focus команд.
- Встроенные keybindings для чата работают нестабильно в разных контекстах.

Статус встроенных биндов Cursor:
- `C:/Users/User/AppData/Roaming/Cursor/User/keybindings.json` оставлен как вторичный/экспериментальный вариант.
- Надёжный вариант для ежедневной работы — именно AHK.

### Персональные алиасы (`introMain.md`)

- `@lightrag ? как меня зовут` -> поиск: `как зовут разработчика в introMain.md`
- `@lightrag ? мой стек` / `@lightrag ? основной технический стек` -> поиск: `основной технологический стек разработчика в introMain.md`
- `@lightrag ? что полезного про меня` -> поиск: `ключевые навыки, опыт и полезная информация о разработчике из introMain.md`

## 7) Правило по `@файл`

- Если это локальный файл в проекте:
  - читать содержимое файла
  - отправлять в `add_text_to_knowledge_base`
- `add_file_to_knowledge_base` использовать только для абсолютного пути на сервере.

## 8) Быстрые проверки

### Проверка LightRAG

```bash
ssh -i "C:\Users\User\.ssh\alexklyvibe" root@193.168.196.12 "curl -sS http://127.0.0.1:9621/health"
```

### Проверка контейнеров

```bash
ssh -i "C:\Users\User\.ssh\alexklyvibe" root@193.168.196.12 "cd /opt/LightRAG && docker compose ps"
```

### Логи LightRAG

```bash
ssh -i "C:\Users\User\.ssh\alexklyvibe" root@193.168.196.12 "cd /opt/LightRAG && docker compose logs --tail=120 lightrag"
```

### Логи oauth2-proxy

```bash
ssh -i "C:\Users\User\.ssh\alexklyvibe" root@193.168.196.12 "docker logs lightrag-auth-oauth2-proxy-1 --tail=120"
```

## 9) После изменений в `.cursor/mcp.json`

1. Перезапустить Cursor (или выключить/включить MCP server).
2. В новом чате проверить:
   - `@lightrag status`
   - `@lightrag ? что есть в базе знаний`

## 9.1) Глобальная команда Cursor (из любого репо)

Настроена user-task:
- `LightRAG: Bootstrap current repo + Reload`

Файл:
- `C:/Users/User/AppData/Roaming/Cursor/User/tasks.json`

Что делает task:
- запускает `bootLightRAG-new-repo.ps1` для текущего `${workspaceFolder}`
- копирует rules/skills (и `.cursor/mcp.json`)
- автоматически отправляет в Cursor команду `workbench.action.reloadWindow` (через AutoHotkey)

Как запустить:
1) `Ctrl+Shift+P`
2) `Tasks: Run Task`
3) выбрать `LightRAG: Bootstrap current repo + Reload`

## 10) Известные ограничения

- `PGGraphStorage` в текущем стеке не используется, так как нужен Apache AGE (`create_graph`), которого нет в `pgvector/pg16`.
- Поэтому граф сейчас `NetworkXStorage`, остальное — PostgreSQL.
- `ENTITY_TYPES` в `1.4.14` может не применяться из env как ожидается (берется дефолтный список).

## 11) Что править в первую очередь при проблемах

- MCP не виден в Cursor:
  - проверить `C:/Users/User/.cursor/mcp.json`
  - перезапустить Cursor
  - проверить ssh ключ `C:/Users/User/.ssh/alexklyvibe`

- `@lightrag` не добавляет документ:
  - `@lightrag status`
  - `@lightrag scan`
  - проверить `/documents` и `pipeline_status`

- OAuth не пускает:
  - проверить redirect URI в Google:
    - `https://lightrag.alexklyvibe.ru/oauth2/callback`
