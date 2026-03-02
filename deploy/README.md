# Развёртывание

## Новый сервер (с нуля)

```bash
# 1. Клонируй репозиторий
git clone git@github.com:thecattest/spring-tickets.git ~/spring-tickets
cd ~/spring-tickets

# 2. Запусти bootstrap — создаст .env из шаблона и остановится
bash deploy/bootstrap.sh

# 3. Заполни секреты
nano .env
#   VK_BOT_TOKEN    — токен бота из настроек группы VK
#   VK_GROUP_ID     — ID группы VK
#   PAYMENTS_PASSWORD — пароль для /payments

# 4. Запусти bootstrap повторно — доделает всё остальное
bash deploy/bootstrap.sh
#   ✓ Системные пакеты (git, redis, nginx)
#   ✓ Python 3.11+ (из deadsnakes PPA если нет в системе)
#   ✓ Виртуальное окружение + зависимости
#   ✓ Схема БД + миграции
#   ✓ Systemd юниты + nginx
#   ✓ Кроны (бэкап БД каждый час, напоминания о должниках в 20:00)
#   ✓ Запуск сервисов

# 5. SSL (когда DNS A-запись заработает)
bash deploy/setup-ssl.sh
```

## Обновление кода

С локальной машины (SSH-хост `tickets` должен быть в `~/.ssh/config`):

```bash
bash deploy/deploy.sh
```

Скрипт: `git pull` → `pip install` → миграции БД → рестарт сервисов.

## Скрипты

| Файл | Что делает | Когда запускать |
|------|-----------|-----------------|
| `bootstrap.sh` | Полная установка с нуля | Один раз на новом сервере |
| `deploy.sh` | Обновление кода + рестарт | При каждом деплое (с локальной машины) |
| `install.sh` | Systemd юниты + nginx | Вызывается из bootstrap |
| `setup-cron.sh` | Крон: напоминания о должниках | Вызывается из bootstrap |
| `setup-backup-cron.sh` | Крон: бэкап БД каждый час | Вызывается из bootstrap |
| `setup-ssl.sh` | Let's Encrypt сертификат | После настройки DNS |
| `aliases.sh` | Bash-алиасы (restart, status, ...) | Вызывается из install.sh |

## Логи

```bash
tail -f ~/spring-tickets/logs/bot.log
tail -f ~/spring-tickets/logs/web.log
tail -f ~/spring-tickets/logs/backup.log
tail -f ~/spring-tickets/logs/debtors_reminders.log
```

Или через journalctl:

```bash
journalctl --user -u tickets-bot -f
journalctl --user -u tickets-web -f
```

## Восстановление из бэкапа

Бэкапы БД сохраняются в `~/tickets-backup/` (формат: `DD.MM-HH.MM.db`) и отправляются в VK.

```bash
# Остановить сервисы
systemctl --user stop tickets-bot tickets-web

# Заменить БД
cp ~/tickets-backup/03.03-14.00.db ~/spring-tickets/tickets.db

# Запустить
systemctl --user start tickets-bot tickets-web
```
