"""
bot/texts.py — Single source of truth for all user-facing bot messages.

Contains module-level string constants extracted from all handler files.
Static strings are plain string assignments.
Parameterized strings use named .format() placeholders.

Wiring (import from this module into handlers) happens in Phase 11.
"""

# ---------------------------------------------------------------------------
# Welcome and help (commands.py)
# ---------------------------------------------------------------------------

WELCOME = (
    "Добро пожаловать в систему бронирования билетов!\n"
    "\n"
    "Я помогу вам оформлять брони для клиентов.\n"
    "\n"
    "Основные команды:\n"
    "Справка - подробная справка\n"
    "Отмена - отменить текущую операцию\n"
    "\n"
    "Чтобы создать бронь:\n"
    "1. Перешлите мне сообщение клиента\n"
    "2. Я попрошу указать ряд\n"
    "3. Введите номера мест\n"
    "4. Получите готовый скрипт для отправки клиенту\n"
    "\n"
    "Начните с пересылки сообщения клиента!"
)
# TODO: описать как провести оплату
HELP = (
    "Справка по работе с ботом\n"
    "\n"
    "СОЗДАНИЕ БРОНИ:\n"
    "1. Перешлите мне сообщение клиента\n"
    "2. Укажите номер ряда (1-24)\n"
    "3. Введите номера мест в одном из форматов:\n"
    "   • Через пробел: 5 6 7\n"
    "   • Через запятую: 5, 6, 7\n"
    "   • Диапазон: 5-7\n"
    "   • Комбинация: 1, 3, 5-7\n"
    "4. Выберите \"Добавить еще\" или \"Готово\"\n"
    "5. Получите скрипт для отправки клиенту\n"
    "\n"
    "ФОРМАТЫ ВВОДА МЕСТ:\n"
    "\"5 6 7\" → места 5, 6, 7\n"
    "\"5, 6, 7\" → места 5, 6, 7\n"
    "\"5-7\" → места 5, 6, 7\n"
    "\"1, 3, 5-7\" → места 1, 3, 5, 6, 7\n"
    "\"1-3, 5, 7-9\" → места 1, 2, 3, 5, 7, 8, 9\n"
    "\n"
    "ВАЖНО:\n"
    "• Бот проверит, что места свободны\n"
    "• Если хотя бы одно место занято - отклонит все\n"
    "• Вы увидите, кто занял место (бронь/резерв)\n"
    "• Можно добавлять места из разных рядов\n"
    "\n"
    "КОМАНДЫ:\n"
    "Справка - эта справка\n"
    "Отмена - отменить текущую операцию\n"
    "Резерв - управление резервами (только для админов)\n"
    "Должники - список должников\n"
    "\n"
    "По вопросам обращайтесь к администратору."
)

# ---------------------------------------------------------------------------
# Cancel messages (commands.py)
# ---------------------------------------------------------------------------

MSG_CANCEL_FULL = (
    "Операция отменена. Состояние сброшено.\n"
    "\n"
    "Чтобы начать заново, перешлите сообщение клиента."
)

MSG_CANCELLED = "Операция отменена."

MSG_CANCEL_ALREADY_IDLE = "Вы уже в начальном состоянии."

MSG_EXIT_FULL = (
    "Сессия завершена. Состояние сброшено.\n"
    "\n"
    "Чтобы начать заново, перешлите сообщение клиента."
)

MSG_EXIT_SHORT = "Сессия завершена."

# ---------------------------------------------------------------------------
# Error messages (ERR_*)
# ---------------------------------------------------------------------------

# Context lost errors
ERR_CONTEXT_LOST = "Ошибка: потерян контекст. Начните заново."
ERR_CONTEXT_LOST_FWD = "Ошибка: потерян контекст. Начните заново с пересылки сообщения."
ERR_CONTEXT_LOST_RESERVE = "Ошибка: потерян контекст. Начните заново с Резерв."

# Database errors
ERR_DB_LOAD_BOOKING = "Ошибка при загрузке брони. Попробуйте позже."
ERR_DB_CHECK_SEATS = "Ошибка при проверке мест. Попробуйте позже."
ERR_DB_ADD_SEATS = "Ошибка при добавлении мест. Попробуйте позже или обратитесь к администратору."
ERR_DB_CREATE_BOOKING = "Ошибка при создании брони. Попробуйте позже или обратитесь к администратору."
ERR_DB_CREATE_BOOKING_SHORT = "Ошибка при создании брони. Попробуйте позже."
ERR_DB_RECORD_PAYMENT = "Ошибка при регистрации оплаты. Попробуйте позже."
ERR_DB_GET_DEBTORS = "Ошибка при получении списка должников."
ERR_DB_GENERATE_SCRIPT = "Ошибка при генерации скрипта. Попробуйте позже."
ERR_DB_CHECK_BOOKING = "Ошибка при проверке брони. Попробуйте позже."

# Permission / registration errors
ERR_NOT_REGISTERED = "Вы не зарегистрированы в системе."
ERR_ACCOUNT_NOT_FOUND = "Ошибка: ваш аккаунт не найден в системе."
ERR_RESERVE_ADMIN_ONLY = "Управление резервами доступно только администраторам."
ERR_PAID_CANCEL_ADMIN_ONLY = "В брони есть оплаченные места. Отмена доступна только админам."

# State / business logic errors
ERR_ALREADY_WORKING = "Вы уже работаете с этим клиентом."
ERR_NO_SEATS_TO_DELETE = "В брони нет мест для удаления."
ERR_NO_SEATS = "В брони нет мест."

# Early row validation (NAV-03)
ERR_ROW_NO_AVAILABLE_SEATS = "Ряд {row}: нет свободных мест. Введите другой ряд:"
ERR_ROW_NO_BOOKED_SEATS = "Ряд {row}: в этой брони нет мест для удаления. Введите другой ряд:"
ERR_ROW_NO_RESERVED_SEATS = "Ряд {row}: нет зарезервированных мест. Введите другой ряд:"

# ---------------------------------------------------------------------------
# Prompt messages (PROMPT_*)
# ---------------------------------------------------------------------------

PROMPT_ENTER_ROW = "Введите номер ряда:"
PROMPT_ENTER_ROW_DELETE = "Введите номер ряда для удаления:"
PROMPT_ENTER_COMMENT = "Введите комментарий для резерва:"
PROMPT_COMMENT_REQUIRED = "Комментарий обязателен. Введите комментарий:"
PROMPT_SELECT_ACTION = "Выберите действие:"
PROMPT_SELECT_QUANTITY = "Выберите количество мест из предложенных кнопок."
PROMPT_MIN_QUANTITY = "Количество мест должно быть не менее 1."

# ---------------------------------------------------------------------------
# Informational messages (MSG_*)
# ---------------------------------------------------------------------------

MSG_CANCELLED_BRIEF = "Отменено."
MSG_BOOKING_CANCELLED = "Бронь отменена."
MSG_NO_DEBTORS = "Должников нет."

# ---------------------------------------------------------------------------
# Parameterized messages (use .format() with named placeholders)
# ---------------------------------------------------------------------------

# Row / seat prompts
MSG_ROW_SEAT_COUNT = (
    "Ряд {row} (мест: {seat_count}).\n"
    "\n"
    "Введите номера мест через пробел, запятую или диапазон.\n"
    "Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
)
MSG_ROW_SEAT_COUNT_WITH_OCCUPIED = (
    "Ряд {row} (мест: {seat_count}). Заняты: {occupied}.\n"
    "\n"
    "Введите номера мест через пробел, запятую или диапазон.\n"
    "Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
)
MSG_ENTER_SEATS_ROW = "Введите номера мест для удаления (ряд {row}, мест: {seat_count}):"
MSG_ENTER_SEATS_DELETE_WITH_BOOKED = "В ряду {row} из этой брони: места {seats}. Какие удалить?"
MSG_ENTER_SEATS_RESERVE = "Введите номера мест для резерва (ряд {row}, мест: {seat_count}):"
MSG_ENTER_SEATS_RESERVE_WITH_OCCUPIED = (
    "Введите номера мест для резерва (ряд {row}, мест: {seat_count}). Заняты: {occupied}."
)
MSG_ENTER_SEATS_UNRESERVE = "Введите номера мест для снятия резерва (ряд {row}, мест: {seat_count}):"

# Validation errors
ERR_INVALID_ROW = "Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"
ERR_INVALID_ROW_FORMAT = "Неверный формат. Введите номер ряда ({min_row}-{max_row}):"
ERR_INVALID_SEATS = (
    "Недопустимые номера мест: {seats}.\n"
    "Для ряда {row} доступны места 1-{seat_count}.\n"
    "\n"
    "Введите другие места:"
)
ERR_PARSE_INPUT = "Ошибка ввода: {error}\n\nПопробуйте снова:"
ERR_QTY_EXCEEDS = (
    "Количество мест превышает доступные для оплаты ({available}). "
    "Введите количество от 1 до {available}:"
)
ERR_INSUFFICIENT_SEATS = "Ошибка: запрошено {requested} мест, но доступно только {available}."

# Seat operation results
MSG_SEATS_ADDED = (
    "Добавлено {count} {count_word}:\n"
    "Ряд {row}, места: {seats}\n"
    "\n"
    "Всего в брони: {total} {total_word}"
)
MSG_SEATS_DELETED = "Удалено {count} {count_word}."
MSG_SEATS_NOT_IN_BOOKING = "Места не принадлежат данной брони: {seats}.\n\nВведите другие места:"
MSG_SEATS_ALREADY_PAID = "Места уже оплачены, удалить нельзя: {seats}.\n\nВведите другие места:"

# Booking creation
MSG_NEW_BOOKING_CREATED = "Создана новая бронь для {name} (ID: {id}).\n\nВведите номер ряда:"
MSG_NEW_BOOKING_NO_RES = (
    "У {name} нет активной брони.\n"
    "Создана новая бронь (ID: {id}).\n"
    "\n"
    "Введите номер ряда:"
)

# Payment
MSG_PAYMENT_SEND_RECEIPT = "Для отметки оплаты перешлите чек (фото или документ)."
MSG_NO_SEATS_FOR_PAYMENT = "У клиента {name} нет мест для оплаты. Все места уже оплачены."
MSG_PAYMENT_ADMIN_NOTIFICATION = (
    "Оплата зафиксирована\n\n"
    "Покупатель: {buyer_name}\n"
    "Билетер: {seller_name}\n"
    "Оплачено {seat_count_word}: {seat_count}\n"
    "Сумма: {amount} руб."
)

# Context switch
MSG_SWITCH_TO_CLIENT = "Переключиться на {name}?\nТекущая операция с {current} будет отменена."
MSG_SWITCH_RECEIPT = "Получен чек от {name}.\nПереключиться с {current} на {name}?"
MSG_SWITCH_PLAIN = "Вы работаете с {current}.\nПереключиться на {name}?"
MSG_CONTINUE_WITH = "Продолжаем работу с {name}."

# Deletion confirmation
MSG_CONFIRM_DELETE_SEATS = "Удалить места:\nРяд {row}: {seats}\n"

# Reserve management
MSG_CONFIRM_UNRESERVE = "Снять резерв:\nРяд {row}: {seats}\n\nПодтвердить?"
MSG_RESERVE_CREATED = "Резерв создан:\nРяд {row}, места: {seats}\nКомментарий: {comment}"
MSG_RESERVE_ACTION_HEADER = "{reserves}\n\nУправление резервами:"

# User management
MSG_USER_ADDED_ADMIN = "Пользователь {name} (vk.com/id{vk_id}) добавлен как администратор."
MSG_USER_ADDED_SELLER = "Пользователь {name} (vk.com/id{vk_id}) добавлен как билетер."
MSG_USER_UPDATED_ADMIN = "Роль {name} (vk.com/id{vk_id}) обновлена на администратор."
MSG_USER_UPDATED_SELLER = "Роль {name} (vk.com/id{vk_id}) обновлена на билетер."
ERR_ADD_USER_NO_FORWARD = "Перешлите сообщение пользователя вместе с командой."
ERR_ADD_USER_FAILED = "Ошибка при добавлении пользователя."
ERR_ADD_USER_ADMIN_ONLY = "Команда доступна только администраторам."
MSG_USER_REMOVED = "Пользователь {name} (vk.com/id{vk_id}) удалён из системы."
ERR_REMOVE_SELF = "Нельзя удалить самого себя."
ERR_USER_NOT_FOUND = "Пользователь не найден в системе."
MSG_USERS_LIST_HEADER = "Пользователи системы:\n\n"
MSG_USERS_LIST_EMPTY = "Нет зарегистрированных пользователей."

# DB errors with detail
ERR_DELETE_SEATS = "Ошибка при удалении мест: {error}"
ERR_CANCEL_BOOKING = "Ошибка при отмене брони: {error}"
ERR_RESERVE_CREATE = "Ошибка при создании резерва: {error}"
ERR_RESERVE_REMOVE = "Ошибка при снятии резерва: {error}"
