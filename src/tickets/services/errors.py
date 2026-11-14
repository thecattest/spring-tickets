"""Ошибки бизнес-правил: их показывают пользователю, а не пишут как сбой."""


class ServiceError(Exception):
    """Базовая ошибка сервисов (в старом слое бота — db.DatabaseError)."""


class NotFoundError(ServiceError):
    """Сущности нет (бронь, пользователь, места)."""


class NotAllowedError(ServiceError):
    """Действие запрещено для этого пользователя (в старом слое — db.PermissionError)."""


class ReservationNotActiveError(ServiceError):
    """Бронь отменена (или её нет): места, оплаты и отмена — только для активной."""

    def __init__(self, reservation_id: int):
        self.reservation_id = reservation_id
        super().__init__(f"Reservation {reservation_id} is not active")


class SeatOccupiedError(ServiceError):
    """Места заняты — в том числе если заняли параллельно, между проверкой и записью."""

    def __init__(self, conflicts: list[dict]):
        """conflicts: [{'row', 'seat', 'status', 'note', 'reservation_id'}, …]"""
        self.conflicts = conflicts
        seats_str = ", ".join(f"{c['row']}/{c['seat']}" for c in conflicts)
        super().__init__(f"Seats already occupied: {seats_str}")


class InsufficientSeatsError(ServiceError):
    """Оплачивается больше мест, чем забронировано и не оплачено."""

    def __init__(self, requested: int, available: int):
        self.requested = requested
        self.available = available
        super().__init__(f"Requested {requested} seats but only {available} BOOKED seats available")
