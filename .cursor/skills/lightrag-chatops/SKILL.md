---
name: lightrag-chatops
description: Query and update LightRAG knowledge base from Cursor chats. Use when user asks to search prior project context, save notes/solutions, or uses commands like @lightrag Найди... / @lightrag Добавь...
---

# LightRAG ChatOps

## When to use

- User asks to recall prior fixes, deployment history, architecture decisions.
- User wants to save a note, troubleshooting result, or code explanation into KB.
- Message contains `@lightrag`.

## Default flow

1. For retrieval:
   - First use repo context for code/implementation questions.
   - If repo context is not enough, call `search_knowledge_base` with `mode: "mix"`.
   - If query is broad, run one broad search then one narrowed follow-up search.
   - If `mix` returns weak/no-context, retry with `mode: "hybrid"` or `mode: "global"`.
2. For text ingestion:
   - Parse text after `@lightrag Добавь`.
   - Call `add_text_to_knowledge_base`.
3. For file ingestion:
   - If file is local in current workspace, read file content and call `upsert_text_to_knowledge_base` with `source_id=<local_path>`.
   - Use `add_file_to_knowledge_base` only for absolute file path that exists on server (with `replace_existing=true` by default).
4. Confirm operation result and report status code/data briefly.

## Command mapping

- `@lightrag Найди <запрос>` -> `search_knowledge_base(query="<запрос>", mode="mix")`
- `@lightrag Добавь в базу знаний <текст>` -> `add_text_to_knowledge_base`
- `@lightrag Добавь в базу знаний @<локальный_файл>` -> read file content -> `upsert_text_to_knowledge_base(text=..., source_id="<локальный_файл>")`
- `@lightrag Добавь в базу знаний файл /opt/...` -> `add_file_to_knowledge_base(file_path="...", replace_existing=true)`
- `@lightrag ? <запрос>` -> `search_knowledge_base(query="<запрос>", mode="mix")`
- `@lightrag + <текст>` -> `add_text_to_knowledge_base`
- `@lightrag + @<локальный_файл>` -> read file content -> `upsert_text_to_knowledge_base(text=..., source_id="<локальный_файл>")`
- `@lightrag + файл /opt/...` -> `add_file_to_knowledge_base(file_path="...", replace_existing=true)`
- `@lightrag scan` -> `scan_inputs_folder`
- `@lightrag status` -> `knowledge_base_status`
- `@lightrag docs` -> `list_documents`

### Smart aliases for `introMain.md`

- `@lightrag Найди как меня зовут` / `@lightrag ? как меня зовут`
  -> `search_knowledge_base(query="как зовут разработчика в introMain.md", mode="mix")`
- `@lightrag Найди мой стек` / `@lightrag ? мой стек` / `@lightrag ? основной технический стек`
  -> `search_knowledge_base(query="основной технологический стек разработчика в introMain.md", mode="mix")`
- `@lightrag Найди что полезного про меня` / `@lightrag ? что полезного про меня`
  -> `search_knowledge_base(query="ключевые навыки, опыт и полезная информация о разработчике из introMain.md", mode="mix")`

## Reliability checks

- If tool error or timeout:
  - Call `knowledge_base_status`.
  - Return exact failure reason.
- If response quality is low:
  - retry with mode `hybrid` or `global`.
- If answer cannot be confirmed from current repo:
  - run MCP lookup before final response.
