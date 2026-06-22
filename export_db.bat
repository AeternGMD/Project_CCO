@echo off
echo ==========================================
echo Exporting database from local Docker container...
echo ==========================================

docker-compose exec -T db mysqldump --skip-ssl -u bot -pbotpassword gdbot > database_dump.sql

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to export database. Is Docker Compose running?
) ELSE (
    echo [SUCCESS] Database exported to database_dump.sql!
    echo Now you can copy database_dump.sql to your server.
)
pause
