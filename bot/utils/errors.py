"""
Centralized error handling for the VK bot.

Provides:
- Custom exception types
- Error logging
- User-friendly error messages
"""

import logging
from typing import Optional
from sqlalchemy.exc import IntegrityError, DatabaseError as SQLDatabaseError
from redis.exceptions import ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)


class BotError(Exception):
    """Base exception for bot errors."""

    def __init__(self, message: str, user_message: Optional[str] = None):
        """
        Initialize bot error.

        Args:
            message: Technical error message (for logs)
            user_message: User-friendly message (for display)
        """
        super().__init__(message)
        self.user_message = user_message or "Произошла ошибка. Попробуйте позже."


class ConfigurationError(BotError):
    """Error in bot configuration."""
    pass


class ValidationError(BotError):
    """Error in user input validation."""
    pass


class StateError(BotError):
    """Error in FSM state management."""
    pass


def handle_database_error(error: Exception) -> str:
    """
    Handle database errors and return user-friendly message.

    Args:
        error: Database exception

    Returns:
        User-friendly error message
    """
    if isinstance(error, IntegrityError):
        logger.error(f"Database integrity error: {error}")

        # Check for seat conflict
        if "seat_assignments_one_active_per_seat" in str(error):
            return "Место уже занято. Обновите список и попробуйте снова."

        # Check for duplicate VK user
        if "vk_user_id" in str(error):
            return "Пользователь уже существует."

        return "Ошибка целостности данных. Обратитесь к администратору."

    elif isinstance(error, SQLDatabaseError):
        logger.error(f"Database error: {error}")
        return "Ошибка базы данных. Попробуйте позже."

    else:
        logger.error(f"Unknown database error: {error}")
        return "Ошибка при работе с базой данных."


def handle_redis_error(error: Exception) -> str:
    """
    Handle Redis connection errors.

    Args:
        error: Redis exception

    Returns:
        User-friendly error message
    """
    if isinstance(error, RedisConnectionError):
        logger.error(f"Redis connection error: {error}")
        return "Ошибка подключения к серверу. Попробуйте позже."

    else:
        logger.error(f"Unknown Redis error: {error}")
        return "Ошибка состояния. Используйте /cancel и попробуйте снова."


def log_error(
    error: Exception,
    context: Optional[dict] = None,
    user_id: Optional[int] = None,
):
    """
    Log error with context.

    Args:
        error: Exception to log
        context: Additional context dictionary
        user_id: VK user ID if available
    """
    context_str = ""
    if context:
        context_str = f" Context: {context}"

    user_str = ""
    if user_id:
        user_str = f" User: {user_id}"

    logger.error(
        f"Error: {type(error).__name__}: {error}{user_str}{context_str}",
        exc_info=True
    )


def format_error_for_user(error: Exception) -> str:
    """
    Format error for display to user.

    Never shows technical details or stack traces.

    Args:
        error: Exception to format

    Returns:
        User-friendly error message
    """
    # Custom bot errors
    if isinstance(error, BotError):
        return error.user_message

    # Database errors
    if isinstance(error, (IntegrityError, SQLDatabaseError)):
        return handle_database_error(error)

    # Redis errors
    if isinstance(error, RedisConnectionError):
        return handle_redis_error(error)

    # Unknown errors
    logger.error(f"Unhandled error: {error}", exc_info=True)
    return "Произошла непредвиденная ошибка. Попробуйте позже или обратитесь к администратору."


# Error message templates
ERROR_MESSAGES = {
    "invalid_row": "Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:",
    "invalid_seat_format": (
        "Неверный формат. Введите номера мест через пробел, запятые или диапазон.\n"
        "Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
    ),
    "invalid_seat_range": "Недопустимые номера мест. Для ряда {row} доступны места 1-{seat_count}.",
    "seat_occupied": (
        "Места уже заняты:\n"
        "• Ряд {row}, место {seat} — {status} ({detail})\n\n"
        "Введите другие места:"
    ),
    "lost_context": "Ошибка: потерян контекст. Начните заново с пересылки сообщения клиента.",
    "database_error": "Ошибка при работе с базой данных. Попробуйте позже или обратитесь к администратору.",
    "redis_error": "Ошибка подключения к серверу. Попробуйте позже.",
    "unknown_error": "Произошла непредвиденная ошибка. Используйте /cancel и попробуйте снова.",
}


def get_error_message(key: str, **kwargs) -> str:
    """
    Get formatted error message by key.

    Args:
        key: Error message key
        **kwargs: Format parameters

    Returns:
        Formatted error message
    """
    template = ERROR_MESSAGES.get(key, ERROR_MESSAGES["unknown_error"])
    return template.format(**kwargs)
