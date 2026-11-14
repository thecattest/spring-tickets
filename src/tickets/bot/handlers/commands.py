"""
Basic bot commands: /start, /help, /cancel, /exit.

These commands are available in any state.
"""

import logging

from vkbottle.bot import Message

from tickets.bot import texts
from tickets.bot.keyboards import commands_keyboard

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

    Back-step navigation: reads FSM_CONFIG[current_state].back_state and
    navigates there instead of clearing to IDLE. Special cases:
    - IDLE: sends "already idle" message (no-op)
    - AWAITING_ROW: checks from_main_menu flag to decide MAIN_MENU vs IDLE
    - CONTEXT_SWITCH_CONFIRM: restores original_state and original_context

    Args:
        message: VK message
        storage: State dispenser instance
    """
    logger.info(f"User {message.from_id} sent /cancel")

    try:
        # Step 1: Read current FSM state
        state_peer = await storage.get(message.from_id)

        # If no state or idle — no-op
        if state_peer is None or "idle" in state_peer.state.lower():
            await message.answer(texts.MSG_CANCEL_ALREADY_IDLE, keyboard=commands_keyboard())
            return

        # Step 2: Convert state string to BotState enum
        # vkbottle stores state as "BotState:awaiting_row" format
        from tickets.bot.fsm.states import BotState

        current_state = BotState(state_peer.state.split(":")[-1])

        # Step 3: Look up back_state from FSM_CONFIG
        from tickets.bot.fsm.config import FSM_CONFIG

        config = FSM_CONFIG.get(current_state)
        back_state = config.back_state if config else None

        # Step 4: Handle special CONTEXT_SWITCH_CONFIRM case (back_state is None)
        if back_state is None and current_state == BotState.CONTEXT_SWITCH_CONFIRM:
            original_state = state_peer.payload.get("original_state")
            original_context = state_peer.payload.get("original_context", {})
            if original_state and original_state != "idle":
                restored = BotState(original_state.split(":")[-1])
                await storage.set(message.from_id, restored, **original_context)
                await message.answer(
                    texts.MSG_CONTINUE_WITH.format(
                        name=original_context.get("buyer_display_name", "")
                    )
                )
                return
            # No restorable state — fall through to clear-to-IDLE below

        # Step 5: Handle None back_state (IDLE or unknown) — clear to IDLE
        if back_state is None:
            await storage.delete(message.from_id)
            await message.answer(texts.MSG_CANCEL_FULL, keyboard=commands_keyboard())
            return

        # Step 6: Handle AWAITING_ROW ambiguity via from_main_menu flag
        if current_state == BotState.AWAITING_ROW:
            from_main_menu = state_peer.payload.get("from_main_menu", False)
            if from_main_menu:
                from tickets.bot.handlers.menu import show_main_menu

                await show_main_menu(
                    message,
                    storage,
                    reservation_id=state_peer.payload["reservation_id"],
                    vk_user_id=state_peer.payload["buyer_vk_user_id"],
                    buyer_display_name=state_peer.payload["buyer_display_name"],
                    buyer_vk_api_id=state_peer.payload["buyer_vk_api_id"],
                )
            else:
                await storage.delete(message.from_id)
                await message.answer(texts.MSG_CANCEL_FULL, keyboard=commands_keyboard())
            return

        # Step 7: Generic back_state navigation
        if back_state == BotState.MAIN_MENU:
            from tickets.bot.handlers.menu import show_main_menu

            await show_main_menu(
                message,
                storage,
                reservation_id=state_peer.payload["reservation_id"],
                vk_user_id=state_peer.payload["buyer_vk_user_id"],
                buyer_display_name=state_peer.payload["buyer_display_name"],
                buyer_vk_api_id=state_peer.payload["buyer_vk_api_id"],
            )
        elif back_state == BotState.RESERVE_ACTION:
            from tickets.bot.keyboards import reserve_action_keyboard
            from tickets.bot.messages import format_reserves_list
            from tickets.bot.utils import db

            reserves = db.get_active_reserves()
            reserves_text = format_reserves_list(reserves)
            await message.answer(
                texts.MSG_RESERVE_ACTION_HEADER.format(reserves=reserves_text),
                keyboard=reserve_action_keyboard(),
            )
            await storage.set(message.from_id, back_state, **state_peer.payload)
        else:
            # Prompt lookup for row-entry states
            from tickets.bot.keyboards import get_empty_keyboard

            _BACK_PROMPTS = {
                BotState.AWAITING_ROW: texts.PROMPT_ENTER_ROW,
                BotState.DELETING_ROW: texts.PROMPT_ENTER_ROW_DELETE,
                BotState.RESERVE_ADDING_ROW: texts.PROMPT_ENTER_ROW,
                BotState.RESERVE_REMOVING_ROW: texts.PROMPT_ENTER_ROW,
            }
            prompt = _BACK_PROMPTS.get(back_state, texts.MSG_CANCELLED)
            await message.answer(prompt, keyboard=get_empty_keyboard())
            await storage.set(message.from_id, back_state, **state_peer.payload)

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
