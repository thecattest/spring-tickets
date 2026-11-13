"""
Константы кнопок и команд бота.

StrEnum-члены являются строками — сравнение через == и `in` работает без .value.
Например: Btn.ADD == "Добавить" is True, Cmd.CANCEL == "Отмена" is True.
"""

from enum import StrEnum


class Btn(StrEnum):
    """Метки кнопок клавиатуры. Используются в Text(...) и сравнениях if text == ..."""

    # commands_keyboard
    CANCEL_CMD = "Отмена"
    HELP_CMD = "Справка"
    DEBTORS_CMD = "Должники"
    RESERVE_CMD = "Резерв"

    # main_menu_keyboard
    ADD = "Добавить"
    DELETE = "Удалить"
    DELETE_ALL = "Удалить все"
    PAYMENT = "Оплата"

    # seat_addition_menu_keyboard
    ADD_MORE = "Добавить еще"
    DONE = "Готово"

    # confirmation_keyboard
    CONFIRM = "Подтвердить"
    CANCEL = "Отмена"

    # context_switch_keyboard
    YES = "Да"
    NO = "Нет"

    # debtors_keyboard
    REFRESH = "Обновить"

    # payment_quantity_keyboard (префикс динамической кнопки "Все N")
    # Используется с text.startswith(Btn.PAY_ALL_PREFIX), не как полная метка кнопки
    PAY_ALL_PREFIX = "Все "


class Cmd(StrEnum):
    """Команды бота. Используются в text= регистрациях и inline-диспетчеризации."""

    START = "start"
    HELP = "Справка"
    HELP_EN = "help"
    CANCEL = "Отмена"
    CANCEL_EN = "cancel"
    DEBTORS = "Должники"
    DEBTORS_EN = "debtors"
    RESERVE = "Резерв"
    RESERVE_EN = "reserve"


# Все известные команды бота — для O(1) проверки `text in ALL_COMMANDS`
ALL_COMMANDS: frozenset[str] = frozenset(Cmd)
