"""
Basic bot commands: /start, /help, /cancel, /exit.

These commands are available in any state.
"""

import logging
from vkbottle.bot import Message

from bot import texts
from bot.keyboards import commands_keyboard

logger = logging.getLogger(__name__)


async def start_handler(message: Message):
    """
    /start command handler.

    Shows welcome message and basic instructions.
    """
    logger.info(f"User {message.from_id} sent /start")

    await message.answer(texts.WELCOME, keyboard=commands_keyboard())


async def help_handler(message: Message):
    """
    /help command handler.

    Shows detailed help and examples.
    """
    logger.info(f"User {message.from_id} sent /help")

    await message.answer(texts.HELP, keyboard=commands_keyboard())


async def cancel_handler(message: Message, storage):
    """
    /cancel command handler.

    Cancels current operation and resets FSM state.

    Args:
        message: VK message
        storage: State dispenser instance
    """
    logger.info(f"User {message.from_id} sent /cancel")

    try:
        # Clear FSM state
        await storage.delete(message.from_id)

        await message.answer(
            texts.MSG_CANCEL_FULL,
            keyboard=commands_keyboard(),
        )
    except Exception as e:
        logger.error(f"Error in /cancel: {e}")
        await message.answer(texts.MSG_CANCELLED)


async def exit_handler(message: Message, storage):
    """
    /exit command handler.

    Hard-resets FSM to IDLE from any state. Unlike /cancel which will later
    support "back one step" navigation (Phase 12), /exit always returns the
    user to the initial idle state regardless of where they are.

    Args:
        message: VK message
        storage: State dispenser instance
    """
    logger.info(f"User {message.from_id} sent /exit")

    try:
        # Clear FSM state (hard reset to IDLE)
        await storage.delete(message.from_id)

        await message.answer(
            texts.MSG_EXIT_FULL,
            keyboard=commands_keyboard(),
        )
    except Exception as e:
        logger.error(f"Error in /exit: {e}")
        await message.answer(texts.MSG_EXIT_SHORT)
