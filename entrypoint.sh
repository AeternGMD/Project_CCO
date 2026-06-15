#!/bin/bash

# Инициализируем директорию данных (если образ чистый)
if [ ! -d "/var/lib/mysql/mysql" ]; then
    mysql_install_db --user=mysql --datadir=/var/lib/mysql
fi

# Запускаем MariaDB в фоне
mysqld_safe &
# Ждем запуска БД
sleep 5

# Создаем базу и пользователя
mysql -u root -e "CREATE DATABASE IF NOT EXISTS gdbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "CREATE USER IF NOT EXISTS 'bot'@'localhost' IDENTIFIED BY 'botpassword';"
mysql -u root -e "GRANT ALL PRIVILEGES ON gdbot.* TO 'bot'@'localhost';"
mysql -u root -e "FLUSH PRIVILEGES;"

# Запускаем бота в активном режиме (чтобы контейнер не завершался)
cd /app
python main.py
