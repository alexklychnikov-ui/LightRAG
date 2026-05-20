import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Chat, Message, Update, User

from telegram_bot.access_control import (
    AccessControlMiddleware,
    _last_deny_notify,
    allowed_user_ids,
    is_access_control_enabled,
    is_user_allowed,
)


class TestAccessControlConfig(unittest.TestCase):
    @patch.dict("os.environ", {"BOT_ALLOWED_USER_IDS": "111,222"}, clear=False)
    def test_allowed_user_ids_parsed(self) -> None:
        self.assertEqual(allowed_user_ids(), frozenset({111, 222}))
        self.assertTrue(is_access_control_enabled())

    @patch.dict(
        "os.environ",
        {"BOT_ALLOWED_USER_IDS": "", "TELEGRAM_BOT_CHATID": "999"},
        clear=False,
    )
    def test_chatid_adds_to_allowed(self) -> None:
        self.assertEqual(allowed_user_ids(), frozenset({999}))

    @patch.dict("os.environ", {"BOT_ALLOWED_USER_IDS": "", "TELEGRAM_BOT_CHATID": ""}, clear=False)
    def test_disabled_when_empty(self) -> None:
        self.assertFalse(is_access_control_enabled())
        self.assertTrue(is_user_allowed(12345, "private"))

    @patch.dict("os.environ", {"BOT_ALLOWED_USER_IDS": "42"}, clear=False)
    def test_deny_unknown_user(self) -> None:
        self.assertFalse(is_user_allowed(1, "private"))

    @patch.dict(
        "os.environ",
        {"BOT_ALLOWED_USER_IDS": "42", "BOT_DENY_GROUP_CHATS": "true"},
        clear=False,
    )
    def test_deny_group_chat(self) -> None:
        self.assertFalse(is_user_allowed(42, "group"))
        self.assertTrue(is_user_allowed(42, "private"))


class TestAccessControlMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _last_deny_notify.clear()

    @patch.dict("os.environ", {"BOT_ALLOWED_USER_IDS": "42"}, clear=False)
    async def test_blocks_unauthorized_message(self) -> None:
        middleware = AccessControlMiddleware()
        handler = AsyncMock(return_value="ok")
        message = Message(
            message_id=1,
            date=0,
            chat=Chat(id=100, type="private"),
            from_user=User(id=1, is_bot=False, first_name="X"),
            text="hi",
        )
        update = Update(update_id=1, message=message)
        bot = AsyncMock()
        result = await middleware(handler, update, {"bot": bot})
        self.assertIsNone(result)
        handler.assert_not_called()
        bot.send_message.assert_awaited()

    @patch.dict("os.environ", {"BOT_ALLOWED_USER_IDS": "42"}, clear=False)
    async def test_allows_authorized_message(self) -> None:
        middleware = AccessControlMiddleware()
        handler = AsyncMock(return_value="ok")
        message = Message(
            message_id=1,
            date=0,
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="Me"),
            text="hi",
        )
        update = Update(update_id=1, message=message)
        result = await middleware(handler, update, {"bot": AsyncMock()})
        self.assertEqual(result, "ok")
        handler.assert_awaited_once()

    @patch.dict("os.environ", {"BOT_ALLOWED_USER_IDS": "42"}, clear=False)
    @patch("telegram_bot.access_control._answer_denied_callback", new_callable=AsyncMock)
    async def test_blocks_unauthorized_callback(self, answer_mock: AsyncMock) -> None:
        middleware = AccessControlMiddleware()
        handler = AsyncMock(return_value="ok")
        cq = CallbackQuery(
            id="1",
            from_user=User(id=1, is_bot=False, first_name="X"),
            chat_instance="x",
            data="mode:qa",
            message=Message(
                message_id=1,
                date=0,
                chat=Chat(id=42, type="private"),
                from_user=User(id=42, is_bot=False, first_name="Me"),
                text="menu",
            ),
        )
        update = Update(update_id=2, callback_query=cq)
        result = await middleware(handler, update, {"bot": AsyncMock()})
        self.assertIsNone(result)
        handler.assert_not_called()
        answer_mock.assert_awaited_once()
