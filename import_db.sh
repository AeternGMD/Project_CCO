#!/bin/bash
echo "=========================================="
echo "Importing database into server Docker container..."
echo "=========================================="

if [ ! -f "database_dump.sql" ]; then
    echo "[ERROR] database_dump.sql not found! Please upload it to this folder first."
    exit 1
fi

cat database_dump.sql | docker-compose exec -T db mysql --skip-ssl -u bot -pbotpassword gdbot

if [ $? -eq 0 ]; then
    echo "[SUCCESS] Database imported successfully!"
else
    echo "[ERROR] Failed to import database. Is Docker Compose running?"
fi
