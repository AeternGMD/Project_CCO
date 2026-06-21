@echo off
echo ==========================================
echo GD Bot - Local Testing Tool (Docker Compose)
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

echo [*] Starting the bot and database using Docker Compose...
docker-compose up -d --build

echo.
echo ==========================================
echo [SUCCESS] Bot and Database are running in the background!
echo To stop them, type: docker-compose down
echo ==========================================
echo.
echo Displaying bot logs (Press Ctrl+C to exit logs):
echo.
docker-compose logs -f bot
pause
