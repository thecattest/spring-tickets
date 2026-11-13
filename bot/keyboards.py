"""
Keyboard generators for VK bot.

Provides inline keyboards for user interactions.
"""

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

from bot.constants import Btn


def commands_keyboard() -> str:
    """
    Persistent keyboard with bot commands, displayed below the input field.

    Layout:
    [/cancel] [/help]
    [/debtors] [/reserve]

    Returns:
        Keyboard JSON
    """
    keyboard = Keyboard(one_time=False, inline=False)

    keyboard.add(Text(Btn.CANCEL_CMD), color=KeyboardButtonColor.NEGATIVE)
    keyboard.add(Text(Btn.HELP_CMD), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(Btn.DEBTORS_CMD), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text(Btn.RESERVE_CMD), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(OpenLink("https://xn----7sbendrvcb5df1a1g.xn--p1ai/payments", label="Оплаты"))
    keyboard.add(
        OpenLink("https://xn----7sbendrvcb5df1a1g.xn--p1ai/concert-day", label="День концерта")
    )

    return keyboard.get_json()


def seat_addition_menu_keyboard() -> Keyboard:
    """
    Keyboard for seat addition menu.

    Buttons:
    - [Добавить еще] - Add more seats (different row)
    - [Готово] - Finish and generate script
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text(Btn.ADD_MORE), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text(Btn.DONE), color=KeyboardButtonColor.POSITIVE)

    return keyboard.get_json()


def get_empty_keyboard() -> str:
    """
    Returns the persistent commands keyboard.

    Used where inline keyboards need to be cleared —
    restores the commands keyboard below the input field.

    Returns:
        Commands keyboard JSON
    """
    return commands_keyboard()


def main_menu_keyboard() -> str:
    """
    Main menu keyboard with 4 action buttons.

    Layout:
    [Добавить] [Удалить]
    [Удалить все] [Оплата]

    Returns:
        Keyboard JSON
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text(Btn.ADD), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text(Btn.DELETE), color=KeyboardButtonColor.NEGATIVE)
    keyboard.row()
    keyboard.add(Text(Btn.DELETE_ALL), color=KeyboardButtonColor.NEGATIVE)
    keyboard.add(Text(Btn.PAYMENT), color=KeyboardButtonColor.POSITIVE)

    return keyboard.get_json()


def confirmation_keyboard() -> str:
    """
    Confirmation keyboard for yes/no actions.

    Layout:
    [Подтвердить] [Отмена]

    Returns:
        Keyboard JSON
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text(Btn.CONFIRM), color=KeyboardButtonColor.POSITIVE)
    keyboard.add(Text(Btn.CANCEL), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()


def context_switch_keyboard() -> str:
    """
    Context switch confirmation keyboard.

    Layout:
    [Да] [Нет]

    Returns:
        Keyboard JSON
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text(Btn.YES), color=KeyboardButtonColor.POSITIVE)
    keyboard.add(Text(Btn.NO), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()


def payment_quantity_keyboard(booked_count: int) -> str:
    """
    Keyboard for selecting payment quantity.

    VK inline keyboard limit: 10 total buttons max.

    Layout:
      booked_count <= 9: numbered buttons 1..N, last one green (= all). No separate "Все".
      booked_count > 9:  numbered buttons 1..8, then "Все N" green.
      Always [Отмена] on last row.

    Examples:
      booked_count=3:  [1][2][3 green] / [Отмена]
      booked_count=7:  [1][2][3][4][5] / [6][7 green] / [Отмена]
      booked_count=1:  [1 green] / [Отмена]
      booked_count=29: [1][2][3][4][5] / [6][7][8] / [Все 29 green] / [Отмена]

    Args:
        booked_count: Number of BOOKED seats available for payment

    Returns:
        Keyboard JSON
    """
    MAX_BUTTONS = 10  # VK inline keyboard total button limit
    keyboard = Keyboard(one_time=False, inline=True)

    if booked_count <= MAX_BUTTONS - 1:
        # Can show all numbers + Отмена (max 10 total)
        show_count = booked_count
        show_all_button = False
    else:
        # Need "Все N": numbers + Все + Отмена = MAX_BUTTONS
        show_count = MAX_BUTTONS - 2  # 8
        show_all_button = True

    buttons_on_current_row = 0

    for i in range(1, show_count + 1):
        if buttons_on_current_row == 5:
            keyboard.row()
            buttons_on_current_row = 0
        is_last = (i == show_count) and not show_all_button
        color = KeyboardButtonColor.POSITIVE if is_last else KeyboardButtonColor.PRIMARY
        keyboard.add(Text(str(i)), color=color)
        buttons_on_current_row += 1

    if show_all_button:
        keyboard.row()
        keyboard.add(
            Text(f"{Btn.PAY_ALL_PREFIX}{booked_count}"), color=KeyboardButtonColor.POSITIVE
        )

    # Отмена always on its own row
    keyboard.row()
    keyboard.add(Text(Btn.CANCEL), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()


def reserve_action_keyboard() -> str:
    """
    Reserve action keyboard for admin reserve management.

    Layout:
    [Добавить резерв] [Удалить резерв]

    Returns:
        Keyboard JSON
    """
    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Text(Btn.ADD), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text(Btn.DELETE), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def debtors_keyboard() -> str:
    """
    Keyboard for the /debtors command view.

    Layout:
    [Обновить]

    Returns:
        Keyboard JSON
    """
    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Text(Btn.REFRESH), color=KeyboardButtonColor.PRIMARY)
    return keyboard.get_json()
