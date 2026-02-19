# Project State

**Last updated:** 2026-02-19
**Current phase:** Milestone v0.2 — Defining requirements

---

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-02-19)

**Core value:** Ни одно место не может быть продано дважды
**Current focus:** v0.2 — Рефакторинг архитектуры бота

---

## Current Status

### Previous Milestone: v0.1 — VK Bot MVP

✅ **Phase 0:** Валидация архитектуры БД
✅ **Phase 1:** Основа бота и создание броней
✅ **Phase 2:** Главное меню и удаление мест
✅ **Phase 3:** Регистрация оплаты
✅ **Phase 4:** Управление резервами (админ)
✅ **Phase 5:** Просмотр должников и напоминания
○ **Phase 6:** Статистика и полировка — deferred to post-refactoring

### Current Milestone: v0.2 — Рефакторинг архитектуры бота

**Status:** Defining requirements

**Goal:** Устранить ~335+ строк дублирования в хендлерах, создать переиспользуемые абстракции (constants, router, steps, texts), улучшить UX навигации (/cancel → назад, /exit → IDLE).

---

## Decisions

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-02-19 | /cancel → назад на шаг, /exit → IDLE | Более естественная навигация | Новое поведение для всех FSM-потоков |
| 2026-02-19 | Ранняя валидация при вводе ряда | Бот не должен ждать номера мест, если в ряду нет мест для операции | Изменение в steps.py + хендлерах |

---

## Open Questions

1. **Порядок миграции хендлеров на router:** По одному файлу или все сразу?
2. **Тестирование после рефакторинга:** Нужны ли новые тесты или достаточно существующих?

---

*State tracking active since: 2026-01-24*
