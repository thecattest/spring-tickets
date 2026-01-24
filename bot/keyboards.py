"""
Keyboard generators for VK bot.

Provides inline keyboards for user interactions.
"""

from vkbottle import Keyboard, KeyboardButtonColor, Text


def seat_addition_menu_keyboard() -> Keyboard:
    """
    Keyboard for seat addition menu.

    Buttons:
    - [Добавить еще] - Add more seats (different row)
    - [Готово] - Finish and generate script
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text("Добавить еще"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("Готово"), color=KeyboardButtonColor.POSITIVE)

    return keyboard.get_json()


def get_empty_keyboard() -> str:
    """
    Get empty keyboard (removes keyboard from chat).

    Returns:
        Empty keyboard JSON with no buttons
    """
    keyboard = Keyboard()
    return keyboard.get_json()


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

    keyboard.add(Text("Добавить"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("Удалить"), color=KeyboardButtonColor.NEGATIVE)
    keyboard.row()
    keyboard.add(Text("Удалить все"), color=KeyboardButtonColor.NEGATIVE)
    keyboard.add(Text("Оплата"), color=KeyboardButtonColor.POSITIVE)

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

    keyboard.add(Text("Подтвердить"), color=KeyboardButtonColor.POSITIVE)
    keyboard.add(Text("Отмена"), color=KeyboardButtonColor.SECONDARY)

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

    keyboard.add(Text("Да"), color=KeyboardButtonColor.POSITIVE)
    keyboard.add(Text("Нет"), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()
