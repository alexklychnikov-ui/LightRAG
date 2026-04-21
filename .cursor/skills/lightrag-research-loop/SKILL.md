---
name: lightrag-research-loop
description: Run a research loop with subagents and persist outcomes to LightRAG. Use when user asks for multi-source investigation, architecture comparison, or long debugging sessions that should be saved to KB.
---

# LightRAG Research Loop

## Goal

Combine subagent exploration with persistent memory in LightRAG.

## Workflow

1. Run subagent(s) for parallel exploration/debugging.
2. Synthesize results into concise findings.
3. Persist findings to KB with `add_text_to_knowledge_base`.
4. Optionally verify retrievability with `search_knowledge_base`.

## Save template

Use this structure for KB entry:

```text
Title: <topic>
Date: <YYYY-MM-DD>
Context: <task or incident>
Findings:
- ...
- ...
Decision:
- ...
Follow-up:
- ...
```

## When to skip save

- User explicitly says "не сохраняй".
- Output contains secrets/tokens/private credentials.
