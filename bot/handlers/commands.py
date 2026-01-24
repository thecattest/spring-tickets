"""
Basic bot commands: /start, /help, /cancel.

These commands are available in any state.
"""

import logging
from vkbottle.bot import Bot, Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage

logger = logging.getLogger(__name__)


async def start_handler(message: Message):
    """
    /start command handler.

    Shows welcome message and basic instructions.
    """
    logger.info(f"User {message.from_id} sent /start")

    text = """Добро пожаловать в систему бронирования билетов!

Я помогу вам оформлять брони для клиентов.

Основные команды:
/help - подробная справка
/cancel - отменить текущую операцию

Чтобы создать бронь:
1. Перешлите мне сообщение клиента
2. Я попрошу указать ряд
3. Введите номера мест
4. Получите готовый скрипт для отправки клиенту

Начните с пересылки сообщения клиента!"""

    await message.answer(text)


async def help_handler(message: Message):
    """
    /help command handler.

    Shows detailed help and examples.
    """
    logger.info(f"User {message.from_id} sent /help")

    text = """Справка по работе с ботом

СОЗДАНИЕ БРОНИ:
1. Перешлите мне сообщение клиента
2. Укажите номер ряда (1-24)
3. Введите номера мест в одном из форматов:
   • Через пробел: 5 6 7
   • Через запятую: 5, 6, 7
   • Диапазон: 5-7
   • Комбинация: 1, 3, 5-7
4. Выберите "Добавить еще" или "Готово"
5. Получите скрипт для отправки клиенту

ФОРМАТЫ ВВОДА МЕСТ:
"5 6 7" → места 5, 6, 7
"5, 6, 7" → места 5, 6, 7
"5-7" → места 5, 6, 7
"1, 3, 5-7" → места 1, 3, 5, 6, 7
"1-3, 5, 7-9" → места 1, 2, 3, 5, 7, 8, 9

ВАЖНО:
• Бот проверит, что места свободны
• Если хотя бы одно место занято - отклонит все
• Вы увидите, кто занял место (бронь/резерв)
• Можно добавлять места из разных рядов

КОМАНДЫ:
/start - приветствие
/help - эта справка
/cancel - отменить текущую операцию

По вопросам обращайтесь к администратору."""

    await message.answer(text)


async def cancel_handler(message: Message):
    """
    /cancel command handler.

    Cancels current operation and resets FSM state.
    """
    logger.info(f"User {message.from_id} sent /cancel")

    # Get storage from bot state dispenser
    bot = message.state_peer.state_dispenser
    if isinstance(bot, RedisStorage):
        # Clear FSM state
        await bot.delete(message.from_id)

        await message.answer(
            "Операция отменена. Состояние сброшено.\n\n"
            "Чтобы начать заново, перешлите сообщение клиента."
        )
    else:
        await message.answer("Операция отменена.")


def register_handlers(bot: Bot):
    """
    Register command handlers with the bot.

    Args:
        bot: VKBottle Bot instance
    """
    # Commands work in any state
    bot.on.message(text="/start")(start_handler)
    bot.on.message(text="/help")(help_handler)
    bot.on.message(text="/cancel")(cancel_handler)

    logger.info("Command handlers registered")
