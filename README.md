# Geometry Dash Local Leaderboard Bot

This bot maintains a local leaderboard of Geometry Dash players, pulling difficulty rankings from Demonlist.org.

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
