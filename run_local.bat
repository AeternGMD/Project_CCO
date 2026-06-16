@echo off
echo ==========================================
echo GD Bot - Local Testing Tool
echo ==========================================

docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not installed or not running!
    echo Please download Docker Desktop from: https://www.docker.com/products/docker-desktop/
    echo Install it, run it, and try again.
    pause
    exit /b
)

IF NOT EXIST ".env" (
    echo [WARNING] .env file not found! Creating a template...
    echo BOT_TOKEN=YOUR_TEST_BOT_TOKEN_HERE > .env
    echo.
    echo Please open the new .env file with Notepad.
    echo Paste your test bot token from @BotFather there.
    echo Then run this script again.
    pause
    exit /b
)

echo [*] Building Docker image (this might take a minute)...
docker build -t gdbot_local .

echo [*] Removing old container if it exists...
docker rm -f gdbot_local_container >nul 2>&1

echo [*] Starting the bot...
docker run -d --name gdbot_local_container gdbot_local

echo.
echo ==========================================
echo [SUCCESS] Bot is running in the background!
echo To stop the bot, type: docker rm -f gdbot_local_container
echo ==========================================
echo.
echo Displaying bot logs (Press Ctrl+C to exit logs):
echo.
docker logs -f gdbot_local_container
pause
