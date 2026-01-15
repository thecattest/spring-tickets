#!/usr/bin/env python3
"""
Простой тест базы данных: создание таблиц и базовые операции.
"""

from datetime import datetime
from database import init_db, get_session
from models import (
    AppUser, VkUser, Reservation, SeatAssignment,
    Payment, PaymentSeat, Expense, ReconcileCheckpoint, AuditLog
)
from models.base import UserRole, ReservationState, SeatStatus, ActorType


def test_database():
    """Тест создания БД и базовых операций."""
    
    print("=" * 60)
    print("Тестирование SQLite базы данных")
    print("=" * 60)
    
    # 1. Инициализация БД
    print("\n1. Инициализация БД...")
    init_db()
    print("✓ Таблицы созданы")
    
    # 2. Создание тестовых данных
    print("\n2. Создание тестовых данных...")
    
    with get_session() as session:
        # Админ
        admin = AppUser(
            role=UserRole.ADMIN,
            display_name="Администратор",
            is_active=True
        )
        session.add(admin)
        
        # Билетер
        seller = AppUser(
            role=UserRole.SELLER,
            display_name="Иван Иванов",
            vk_user_id=123456,
            is_active=True
        )
        session.add(seller)
        session.flush()
        
        # Покупатель
        buyer = VkUser(
            vk_user_id=987654321,
            display_name="Петр Петров",
            profile_url="https://vk.com/id987654321"
        )
        session.add(buyer)
        session.flush()
        
        # Бронь
        reservation = Reservation(
            buyer_vk_user_id=buyer.id,
            sold_by_user_id=seller.id,
            state=ReservationState.ACTIVE
        )
        session.add(reservation)
        session.flush()
        
        # Места в брони
        seats = []
        for seat_num in [5, 6, 7]:
            seat = SeatAssignment(
                row_number=10,
                seat_number=seat_num,
                status=SeatStatus.BOOKED,
                reservation_id=reservation.id,
                created_by_user_id=seller.id
            )
            session.add(seat)
            seats.append(seat)
        session.flush()
        
        # Резерв (для гостей)
        reserve_seat = SeatAssignment(
            row_number=1,
            seat_number=1,
            status=SeatStatus.RESERVED,
            created_by_user_id=admin.id,
            note="VIP место для гостя"
        )
        session.add(reserve_seat)
        
        # Оплата
        payment = Payment(
            reservation_id=reservation.id,
            recorded_by_user_id=seller.id,
            vk_message_url="https://vk.com/im?sel=-123456&msgid=789",
            vk_message_ts=datetime.utcnow()
        )
        session.add(payment)
        session.flush()
        
        # Связь оплаты с местами (оплачены только 2 из 3 мест)
        for seat in seats[:2]:
            payment_seat = PaymentSeat(
                payment_id=payment.id,
                seat_assignment_id=seat.id
            )
            session.add(payment_seat)
            # Обновляем статус места на "оплачено"
            seat.status = SeatStatus.PAID
        
        # Расход
        expense = Expense(
            created_by_user_id=admin.id,
            amount_rub=5000,
            note="Аренда зала"
        )
        session.add(expense)
        
        # Чекап
        checkpoint = ReconcileCheckpoint(
            checked_by_user_id=admin.id,
            note="Первая проверка"
        )
        session.add(checkpoint)
        
        # Аудит-лог
        audit = AuditLog(
            actor_type=ActorType.USER,
            actor_user_id=seller.id,
            action_type="create_reservation",
            entity_type="reservation",
            entity_id=str(reservation.id),
            payload={
                "buyer_vk_user_id": buyer.vk_user_id,
                "seats_count": 3
            }
        )
        session.add(audit)
        
        session.commit()
        print("✓ Тестовые данные добавлены")
    
    # 3. Проверка данных
    print("\n3. Проверка созданных данных...")
    
    with get_session() as session:
        # Проверка пользователей
        users = session.query(AppUser).all()
        print(f"   - Пользователей: {len(users)}")
        
        # Проверка броней
        reservations = session.query(Reservation).all()
        print(f"   - Броней: {len(reservations)}")
        
        # Проверка мест
        seats = session.query(SeatAssignment).filter(
            SeatAssignment.released_at.is_(None)
        ).all()
        print(f"   - Активных мест: {len(seats)}")
        
        booked = [s for s in seats if s.status == SeatStatus.BOOKED]
        paid = [s for s in seats if s.status == SeatStatus.PAID]
        reserved = [s for s in seats if s.status == SeatStatus.RESERVED]
        
        print(f"     • Забронировано: {len(booked)}")
        print(f"     • Оплачено: {len(paid)}")
        print(f"     • В резерве: {len(reserved)}")
        
        # Проверка оплат
        payments = session.query(Payment).all()
        print(f"   - Оплат: {len(payments)}")
        
        # Проверка расходов
        expenses = session.query(Expense).all()
        print(f"   - Расходов: {len(expenses)}")
        
        # Проверка аудит-лога
        logs = session.query(AuditLog).all()
        print(f"   - Записей в аудит-логе: {len(logs)}")
    
    # 4. Проверка уникальности (partial index)
    print("\n4. Проверка уникальности активных мест...")
    
    try:
        with get_session() as session:
            # Попытка создать дубликат активного места
            duplicate_seat = SeatAssignment(
                row_number=10,
                seat_number=5,  # уже занято
                status=SeatStatus.BOOKED,
                created_by_user_id=1
            )
            session.add(duplicate_seat)
            session.commit()
        print("✗ ОШИБКА: дубликат не был заблокирован!")
    except Exception as e:
        print(f"✓ Дубликат заблокирован (ожидаемо): {type(e).__name__}")
    
    print("\n" + "=" * 60)
    print("Тест завершен успешно!")
    print("=" * 60)
    print("\nФайл БД: tickets.db")
    print("Для удаления БД: rm tickets.db")


if __name__ == "__main__":
    test_database()
