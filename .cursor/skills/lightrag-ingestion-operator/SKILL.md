---
name: lightrag-ingestion-operator
description: Maintain LightRAG ingestion quality and keep KB consistent. Use when user asks to add many docs, reindex after storage changes, deduplicate, or verify indexing pipeline.
---

# LightRAG Ingestion Operator

## Use cases

- Bulk add/reindex after migration.
- Check why docs are not visible in search.
- Run safe ingestion verification loop.

## Workflow

1. Check status:
   - `knowledge_base_status`
   - `list_documents`
2. If no new files indexed:
   - confirm source folder and invoke `scan_inputs_folder`.
3. Poll until pipeline is idle before final report.
4. Share compact report:
   - indexed count
   - failed count
   - next action

## Safety rules

- Do not call delete endpoints automatically.
- Do not overwrite existing data without explicit user request.
- Keep ingestion idempotent: prefer scan + status checks over repeated blind uploads.
