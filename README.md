# Geometry Dash Local Leaderboard Bot

This bot maintains a local leaderboard of Geometry Dash players, pulling difficulty rankings from Demonlist.org.

## Запись рекордов без кавычек

```text
/r Mr Spaced Theory of Everything 2
/r Mr Spaced: Tidal Wave, Bloodbath
/r Mr Spaced: Tidal Wave = 60% | 40-100
/r Mr Spaced: Tidal Wave = 60%, Bloodbath
/r @42: #1537, #1538
/dr Mr Spaced: Theory of Everything 2
```

- По умолчанию зачисляется 100%. Пробелы и цифры в именах разрешены.
- `:` явно отделяет ник от уровней, `=` отделяет прогресс. Старый формат
  с кавычками и прогрессом без `=` поддерживается.
- Поиск точный, без учёта регистра и повторных пробелов. Нет нечёткого
  автозачисления похожим именам. Например, если подходят `Mr` + `Spaced Tidal Wave`
  и `Mr Spaced` + `Tidal Wave`, бот предлагает выбор.
- Если существуют `Level 60` и `Level`, ввод `Level 60` допускает два варианта:
  прохождение первого или 60% второго. Бот не выбирает за администратора.
- `@42` — внутренний ID игрока в базе бота, не Telegram ID.
  `#1537` — ID уровня Demonlist, не Geometry Dash ID. Эти ID показываются
  в описаниях вариантов, а также в `/profile` и `/level` соответственно.
  Для названий с зарезервированными `, : = |`
  можно использовать ID или кавычки.
- Все неоднозначности разрешаются до записи. Выбор действует 5 минут,
  доступен только автору команды и не может повторно записать рекорды.
  При неизвестном названии или неверном формате вся команда отклоняется.
  Ошибка БД или Telegram уже во время исполнения может прервать обработку;
  ранее выполненные записи не откатываются как одна общая транзакция.
- До 100 уровней за команду; одинаковые ID/прогрессы записываются один раз.
  `/dr` использует тот же разбор, но удаляет рекорды на указанных уровнях.

Индекс имён строится лениво двумя узкими SELECT-запросами и затем используется
в памяти. Он сбрасывается при изменении игроков, обновлении уровней и восстановлении
БД. Через 5 минут индекс также перечитывается при следующем обращении, чтобы учесть
внешние изменения БД. Во время простоя запросов для индекса нет.
В памяти хранятся максимум 64 незавершённых выбора, до 200 вариантов на команду.

Проверить стоимость разбора без БД и Telegram:

```bash
python scripts/benchmark_record_resolver.py
python -m unittest discover -s tests -v
```

## Тихое ежечасное обновление

Внутри процесса бота работает одна асинхронная задача: первый запуск через час
после старта, далее каждый час по монотонному таймеру. Обновляются только уровни;
профили игроков автоматически не обходятся. Результат и ошибки попадают только
в серверный лог. В Telegram эта задача ничего не отправляет.

Ручной `/info_update` и автоматическая задача используют общую блокировку.
Повторное обновление во время текущего не ставится в очередь. На один запуск
отведено не более 120 секунд; при ошибке плановая задача продолжает работу в
следующий час. Список скачивается по 50 уровней, максимум 20 HTTP-запросов
одновременно (около 40 запросов для списка из 1800–1900 уровней).
Запись списка в MariaDB выполняется в транзакции: при ошибке или отмене — rollback.
При выключении бота задача отменяется до закрытия пула БД.
Блокировка рассчитана на один экземпляр polling-бота, как в текущем Compose.

После получения нужной ветки из GitHub пересоберите бот:

```bash
docker compose up -d --build bot
docker compose logs --tail=100 bot
```

## Setup Instructions

1. Clone or copy the bot code to your server.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and configure variables:
   - `BOT_TOKEN`: Your Telegram Bot Token (from BotFather)
   - `CHANNEL_ID`: ID of your Telegram channel (e.g., `-100123456789`)
   - `ROOT_ID`: Your Telegram ID to access `/add_admin`

## Running Locally

```bash
python main.py
```

## Systemd Deployment (Linux)

To run the bot in the background automatically, create a systemd service:

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/gdbot.service
   ```

2. Paste the following configuration (adjust paths):
   ```ini
   [Unit]
   Description=Geometry Dash Leaderboard Bot
   After=network.target

   [Service]
   User=your_user
   Group=your_group
   WorkingDirectory=/path/to/gd_bot
   Environment="PATH=/path/to/gd_bot/venv/bin"
   ExecStart=/path/to/gd_bot/venv/bin/python main.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable gdbot
   sudo systemctl start gdbot
   ```

4. View logs:
   ```bash
   journalctl -u gdbot -f
   ```
