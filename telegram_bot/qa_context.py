import asyncio
import os
import time
from dataclasses import dataclass, field


def _idle_seconds() -> float | None:
    raw = os.getenv("BOT_QA_SESSION_IDLE_MINUTES", "20").strip().lower()
    if raw in {"", "0", "off", "false", "no", "disable", "none"}:
        return None
    try:
        minutes = float(raw)
    except ValueError:
        return 20 * 60
    if minutes <= 0:
        return None
    return minutes * 60


def qa_session_ttl_enabled() -> bool:
    return _idle_seconds() is not None


def _max_stored_messages() -> int:
    return max(2, min(int(os.getenv("BOT_QA_CONTEXT_MAX_MESSAGES", "24")), 80))


def _max_context_chars() -> int:
    return max(800, min(int(os.getenv("BOT_QA_CONTEXT_MAX_CHARS", "7000")), 28000))


def _clip_text(text: str, max_len: int = 4500) -> str:
    value = (text or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 30].rstrip() + "\n…[фрагмент обрезан]"


def _format_messages_block(messages: list[dict[str, str | float]]) -> str:
    lines: list[str] = []
    for m in messages:
        role = str(m.get("role", ""))
        text = str(m.get("text", "")).strip()
        if not text:
            continue
        label = "Пользователь" if role == "user" else "Ассистент"
        lines.append(f"[{label}] {text}")
    return "\n".join(lines)


@dataclass
class _ChatSession:
    messages: list[dict[str, str | float]] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)


class QaConversationStore:
    def __init__(self) -> None:
        self._sessions: dict[int, _ChatSession] = {}
        self._lock = asyncio.Lock()

    async def clear(self, chat_id: int) -> None:
        async with self._lock:
            self._sessions.pop(chat_id, None)

    def _trim_session(self, session: _ChatSession) -> None:
        max_msgs = _max_stored_messages()
        while len(session.messages) > max_msgs:
            session.messages.pop(0)
        max_chars = _max_context_chars()
        while session.messages:
            block = _format_messages_block(session.messages)
            if len(block) <= max_chars:
                break
            session.messages.pop(0)

    async def expire_if_idle(self, chat_id: int, now: float | None = None) -> None:
        idle = _idle_seconds()
        if idle is None:
            return
        ts = now if now is not None else time.time()
        async with self._lock:
            session = self._sessions.get(chat_id)
            if not session:
                return
            if ts - session.last_activity > idle:
                self._sessions.pop(chat_id, None)

    async def prune_stale_sessions(self, now: float | None = None) -> int:
        idle = _idle_seconds()
        if idle is None:
            return 0
        ts = now if now is not None else time.time()
        removed = 0
        async with self._lock:
            dead: list[int] = []
            for cid, session in self._sessions.items():
                if ts - session.last_activity > idle:
                    dead.append(cid)
            for cid in dead:
                self._sessions.pop(cid, None)
                removed += 1
        return removed

    async def get_dialog_context_block(self, chat_id: int) -> str:
        async with self._lock:
            session = self._sessions.get(chat_id)
            if not session or not session.messages:
                return ""
            return _format_messages_block(session.messages).strip()

    async def build_contextual_query(self, chat_id: int, current_question: str) -> str:
        q = (current_question or "").strip()
        async with self._lock:
            session = self._sessions.get(chat_id)
            if not session or not session.messages:
                return q
            block = _format_messages_block(session.messages)
            if not block.strip():
                return q
        return (
            "Учитывай предыдущий диалог в этом чате при ответе на последний вопрос. "
            "Если новый вопрос — уточнение к прошлому, опирайся на контекст.\n\n"
            "--- Контекст диалога ---\n"
            f"{block}\n"
            "--- Конец контекста ---\n\n"
            f"Текущий вопрос:\n{q}"
        )

    async def record_exchange(
        self,
        chat_id: int,
        user_text: str,
        assistant_text: str,
    ) -> None:
        now = time.time()
        u = _clip_text(user_text)
        a = _clip_text(assistant_text)
        async with self._lock:
            session = self._sessions.setdefault(chat_id, _ChatSession())
            session.messages.append({"role": "user", "text": u, "ts": now})
            session.messages.append({"role": "assistant", "text": a, "ts": now})
            session.last_activity = now
            self._trim_session(session)


qa_conversation_store = QaConversationStore()


async def session_prune_loop(interval_seconds: float = 60.0) -> None:
    if _idle_seconds() is None:
        return
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await qa_conversation_store.prune_stale_sessions()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
