"""
Регистрация хендлеров бота — порядок важен: vkbottle вызывает первый подходящий.

  1. Команды пользователей (/addadmin, /addseller, /removeuser) — до пересылки:
     они тоже приходят с пересланным сообщением.
  2. Сообщение о покупателе (пересылка, ответ, ссылка на профиль) — в любом состоянии.
  3. Команды (/start, /help, «Отмена», /exit, «Резерв», «Должники», …) — до
     состояний: «Отмена» посреди ввода мест — это команда, а не ввод.
  4. Хендлеры состояний FSM с проверкой роли из FSM_CONFIG.
"""

import logging

from vkbottle.framework.labeler.bot import BotLabeler

from tickets.bot import auth, vk
from tickets.bot.flows import booking, debtors, deletion, menu, navigation, payment, reserve, users
from tickets.bot.fsm.config import FSM_CONFIG
from tickets.bot.fsm.states import BotState
from tickets.bot.fsm.storage import RedisStorage

logger = logging.getLogger(__name__)

STATE_HANDLERS = {
    BotState.AWAITING_ROW: booking.on_row,
    BotState.AWAITING_SEATS: booking.on_seats,
    BotState.SEAT_ADDITION_MENU: booking.on_addition_menu,
    BotState.MAIN_MENU: menu.on_menu_button,
    BotState.CONTEXT_SWITCH_CONFIRM: menu.on_switch_answer,
    BotState.DELETING_ROW: deletion.on_row,
    BotState.DELETING_SEATS: deletion.on_seats,
    BotState.DELETION_CONFIRM: deletion.on_delete_confirm,
    BotState.CANCEL_CONFIRM: deletion.on_cancel_confirm,
    BotState.PAYMENT_QUANTITY: payment.on_quantity,
    BotState.RESERVE_ACTION: reserve.on_action,
    BotState.RESERVE_ADDING_ROW: reserve.on_adding_row,
    BotState.RESERVE_ADDING_SEATS: reserve.on_adding_seats,
    BotState.RESERVE_COMMENT: reserve.on_comment,
    BotState.RESERVE_REMOVING_ROW: reserve.on_removing_row,
    BotState.RESERVE_REMOVING_SEATS: reserve.on_removing_seats,
    BotState.RESERVE_REMOVE_CONFIRM: reserve.on_remove_confirm,
}


class Router:
    """router = Router(storage); router.register_all(); bot.labeler.load(router.labeler)"""

    def __init__(self, storage: RedisStorage):
        self.labeler = BotLabeler()
        self.storage = storage

    def _with_storage(self, handler):
        storage = self.storage

        async def wrapped(message):
            await handler(message, storage)

        wrapped.__name__ = handler.__name__
        return wrapped

    def register_all(self) -> None:
        on = self.labeler.message

        on(text=["addadmin", "/addadmin"])(users.on_add_admin)
        on(text=["addseller", "/addseller"])(users.on_add_seller)
        on(text=["removeuser", "/removeuser"])(users.on_remove)

        on(func=vk.mentions_buyer)(self._with_storage(booking.on_buyer))

        on(text=["/start", "start"])(navigation.on_start)
        on(text=["Справка", "/help", "help"])(navigation.on_help)
        on(text=["Отмена", "/cancel", "cancel"])(self._with_storage(navigation.on_cancel))
        on(text=["Выход", "/exit", "exit"])(self._with_storage(navigation.on_exit))
        on(text=["Резерв", "/reserve", "reserve"])(self._with_storage(reserve.on_command))
        on(text=["Должники", "/debtors", "debtors", "Обновить"])(debtors.on_debtors)
        on(text=["users", "/users", "Пользователи"])(users.on_list)

        for state, handler in STATE_HANDLERS.items():
            guard = FSM_CONFIG[state].auth_guard
            on(state=state)(auth.guard_state(handler, guard, self.storage))

        logger.info("Router: %d handlers registered", len(self.labeler.message_view.handlers))
