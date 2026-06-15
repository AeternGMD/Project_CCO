@echo off
chcp 65001 >nul
echo ==========================================
echo GD Bot - Инструмент локального тестирования
echo ==========================================

:: Проверка установки Docker
docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Docker не установлен или не запущен!
    echo Скачайте Docker Desktop с официального сайта: https://www.docker.com/products/docker-desktop/
    echo Установите его, запустите и попробуйте снова.
    pause
    exit /b
)

:: Проверка наличия .env файла
IF NOT EXIST ".env" (
    echo [ВНИМАНИЕ] Файл .env не найден! Создаю шаблон...
    echo BOT_TOKEN=ВАШ_ТОКЕН_ДЛЯ_ТЕСТОВОГО_БОТА > .env
    echo.
    echo Пожалуйста, откройте появившийся файл .env через Блокнот.
    echo Вставьте туда токен вашего тестового бота (от @BotFather).
    echo После этого запустите этот скрипт еще раз.
    pause
    exit /b
)

echo [*] Собираю образ Docker (это может занять минутку)...
docker build -t gdbot_local .

echo [*] Удаляю старый контейнер (если он был)...
docker rm -f gdbot_local_container >nul 2>&1

echo [*] Запускаю бота...
docker run -d --name gdbot_local_container gdbot_local

echo.
echo ==========================================
echo [УСПЕХ] Бот запущен и работает в фоне!
echo Чтобы остановить бота, введите команду: docker rm -f gdbot_local_container
echo ==========================================
echo.
echo Сейчас я выведу логи бота (чтобы выйти из логов, нажмите Ctrl+C):
echo.
docker logs -f gdbot_local_container
pause
