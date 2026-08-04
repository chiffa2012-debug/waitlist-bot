# Telegram-бот «Лист ожидания»

Простой внутренний бот для администратора салона: хранит заявки в SQLite, показывает список на сегодня/завтра и периодически проверяет свободные окна в Yclients. Клиентам бот не пишет и реальные записи в Yclients не создаёт.

## Безопасность токена

Если Telegram Bot API token когда-либо отправлялся в чат, считайте его скомпрометированным и **перевыпустите через BotFather**. Не вставляйте токен в код или git. Единственное место для него — локальный файл `.env`:

```env
TELEGRAM_BOT_TOKEN=...
```

Файл `.env` уже исключён из git.

## Возможности

- `/start` — главное меню;
- `/add` — пошагово добавить имя, телефон, дату, время и комментарий;
- `/list`, `/today`, `/tomorrow` — показать активные заявки;
- `/done`, `/delete` — изменить статус после подтверждения;
- `/check` — вручную проверить окна;
- `/admins`, `/add_admin`, `/remove_admin` — управление администраторами владельцем;
- автоматическая проверка по расписанию;
- уведомление не чаще одного раза в 6 часов на заявку;
- владелец и управляемый список администраторов;
- mock-режим без Yclients по умолчанию.

Дата понимается и в естественных вариантах: `на завтра`, `завтра в 16:00`, `16:00 завтра`, `25.07.2026`, `2026-07-25`. Если дата и время указаны вместе, бот сразу переходит к комментарию. Текущий шаг анкеты хранится в SQLite и не теряется после перезапуска бота.

Статусы: `waiting`, `notified`, `booked`, `deleted`.

## Структура

```text
telegram-waitlist-bot/
├── bot/
│   ├── __init__.py
│   ├── access.py
│   ├── config.py
│   ├── db.py
│   ├── handlers.py
│   ├── keyboards.py
│   ├── main.py
│   ├── models.py
│   ├── repositories.py
│   ├── scheduler.py
│   ├── states.py
│   ├── utils.py
│   └── yclients_client.py
├── tests/
│   ├── test_date_parser.py
│   ├── test_phone_validation.py
│   ├── test_repository.py
│   └── test_yclients_client.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
└── README.md
```

## Локальный запуск

Нужен Python 3.11 или новее.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Откройте `.env`, укажите новый `TELEGRAM_BOT_TOKEN` и желательно `ADMIN_TELEGRAM_ID`. Затем:

```powershell
python -m bot.main --smoke-check
python -m pytest
python -m bot.main
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m bot.main --smoke-check
python -m pytest
python -m bot.main
```

Если `ADMIN_TELEGRAM_ID` пуст, первый пользователь, который отправит `/start`, становится владельцем. Владелец может открыть кнопку «Администраторы» и добавлять или удалять других администраторов по их числовому Telegram ID. Самого владельца удалить нельзя. Новый администратор должен хотя бы один раз открыть бота и отправить `/start`, иначе Telegram не позволит боту присылать ему уведомления.

Обычные администраторы могут работать с листом ожидания, но не могут менять список администраторов. Уведомления о найденных окнах отправляются всем добавленным администраторам.

## Docker

1. Скопируйте `.env.example` в `.env`.
2. Заполните новый Telegram token и ID администратора.
3. Запустите:

```bash
docker compose up -d --build
docker compose logs -f waitlist-bot
```

SQLite хранится в Docker volume `waitlist_data` и переживает перезапуск контейнера.

## Подключение Yclients

По умолчанию интеграция выключена, поэтому бот полностью работает как локальный лист ожидания. `/check` честно сообщает, что проверка выключена.

Для реального чтения окон заполните:

```env
YCLIENTS_ENABLED=true
YCLIENTS_BEARER_TOKEN=...
YCLIENTS_USER_TOKEN=...
YCLIENTS_COMPANY_ID=...
YCLIENTS_SERVICE_ID=...
YCLIENTS_STAFF_ID=
YCLIENTS_CHECK_INTERVAL_MINUTES=15
```

`YCLIENTS_SERVICE_ID` — ID одной онлайн-доступной услуги, окна которой отслеживает этот простой MVP. `YCLIENTS_STAFF_ID` необязателен: без него проверяются все доступные для услуги мастера, с ним — только выбранный мастер.

Интеграция использует проверенные read-only маршруты Yclients API v1:

- `GET /book_staff/{company_id}?service_id=...`;
- `GET /book_times/{company_id}/{staff_id}/{date}?service_ids[]=...`.

Авторизация передаётся заголовком `Authorization: Bearer ..., User ...`. Ответы и ошибки логируются кратко, токены не логируются. Никаких write-запросов к Yclients в проекте нет.

Если у салона разные услуги, мастера или длительности, следующий продуктовый шаг — добавить `service_id`/`staff_id` в каждую заявку. В текущем MVP они глобальные, чтобы интерфейс оставался быстрым и соответствовал заданной анкете.

Для салона «Кудри» замените `TIMEZONE=Europe/Amsterdam` на `TIMEZONE=Asia/Irkutsk`.

## Smoke-check

Без подключения к Telegram и Yclients:

```bash
python -m bot.main --smoke-check
```

Команда проверяет загрузку конфигурации, создание схемы SQLite и чтение активных заявок. Для неё всё равно нужен синтаксически заполненный `TELEGRAM_BOT_TOKEN`; сетевой запрос не выполняется.

Полные тесты:

```bash
python -m pytest -q
```

Ручной сценарий:

1. `/start` — появилось меню.
2. `/add` — добавить тестового клиента и подтвердить.
3. `/list` — заявка видна со статусом `ожидает`.
4. `/check` при `YCLIENTS_ENABLED=false` — понятное сообщение, без падения.
5. Нажать «Записан» → подтвердить → заявка исчезла из активного списка.
6. Написать боту со второго Telegram-аккаунта → доступ отклонён.

## Допущения

1. Бот — внутренний инструмент одного администратора, без ролей и Mini App.
2. Он только обнаруживает потенциальные окна; администратор сам связывается с клиентом и оформляет запись.
3. Услуга и мастер для проверки задаются глобально через `.env`, потому что обязательная анкета заявки не содержит этих полей.
4. Телефон сохраняется как введён; проверяется только наличие минимум 7 цифр.
5. Даты «сегодня» и «завтра» вычисляются в `TIMEZONE`.
6. Повторное уведомление по одной заявке разрешено через 6 часов, если она всё ещё активна.
