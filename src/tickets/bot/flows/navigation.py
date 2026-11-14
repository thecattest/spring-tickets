"""Команды в любом состоянии: /start, /help, /cancel (шаг назад), /exit (сброс)."""

import logging

from vkbottle.bot import Message

from tickets.bot import texts, vk
from tickets.bot.flows import menu, reserve
from tickets.bot.fsm.config import FSM_CONFIG
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage
from tickets.bot.keyboards import commands_keyboard, get_empty_keyboard

logger = logging.getLogger(__name__)

# Подсказка после шага назад в состояние ввода ряда
_BACK_PROMPTS = {
    BotState.AWAITING_ROW: texts.PROMPT_ENTER_ROW,
    BotState.DELETING_ROW: texts.PROMPT_ENTER_ROW_DELETE,
    BotState.RESERVE_ADDING_ROW: texts.PROMPT_ENTER_ROW,
    BotState.RESERVE_REMOVING_ROW: texts.PROMPT_ENTER_ROW,
}


async def on_start(message: Message) -> None:
    await vk.answer(message, texts.WELCOME, keyboard=commands_keyboard())


async def on_help(message: Message) -> None:
    await vk.answer(message, texts.HELP, keyboard=commands_keyboard())


async def on_exit(message: Message, storage: RedisStorage) -> None:
    """/exit — сброс состояния из любого места."""
    await storage.reset(message.from_id)
    await vk.answer(message, texts.MSG_EXIT_FULL, keyboard=commands_keyboard())


async def _cancel_to_idle(message: Message, storage: RedisStorage) -> None:
    await storage.reset(message.from_id)
    await vk.answer(message, texts.MSG_CANCEL_FULL, keyboard=commands_keyboard())


async def on_cancel(message: Message, storage: RedisStorage) -> None:
    """
    /cancel (и кнопка «Отмена») — шаг назад по FSM_CONFIG[state].back_state:
    в меню брони, к вводу ряда, к действиям резерва; из ввода ряда новой
    брони и из переключения клиента — особые случаи.
    """
    state, context = await storage.load(message.from_id)
    if state is None or state == BotState.IDLE:
        await vk.answer(message, texts.MSG_CANCEL_ALREADY_IDLE, keyboard=commands_keyboard())
        return

    if state == BotState.CONTEXT_SWITCH_CONFIRM:
        saved = context.saved
        if saved and saved.state != BotState.IDLE:
            await storage.save(message.from_id, saved.state, saved.context)
            name = saved.context.client.buyer_name if saved.context.client else ""
            await vk.answer(message, texts.MSG_CONTINUE_WITH.format(name=name))
            return
        await _cancel_to_idle(message, storage)
        return

    back = FSM_CONFIG[state].back_state
    if back is None:
        await _cancel_to_idle(message, storage)
        return

    # Ввод ряда: из меню брони — обратно в меню, в новой брони — выход
    if state == BotState.AWAITING_ROW and not context.from_main_menu:
        await _cancel_to_idle(message, storage)
        return
    if back == BotState.MAIN_MENU or state == BotState.AWAITING_ROW:
        if context.client is None:
            await _cancel_to_idle(message, storage)
            return
        await menu.show(message, storage, context.client)
        return

    if back == BotState.RESERVE_ACTION and context.admin_user_id is not None:
        await reserve.show_actions(message, storage, context.admin_user_id)
        return

    await vk.answer(
        message, _BACK_PROMPTS.get(back, texts.MSG_CANCELLED), keyboard=get_empty_keyboard()
    )
    await storage.save(message.from_id, back, context)
