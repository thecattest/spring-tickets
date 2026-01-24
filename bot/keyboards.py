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
        Empty keyboard JSON
    """
    keyboard = Keyboard()
    return keyboard.get_empty_keyboard()
