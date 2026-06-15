#!/bin/bash

# Инициализируем директорию данных (если образ чистый)
if [ ! -d "/var/lib/mysql/mysql" ]; then
    mysql_install_db --user=mysql --datadir=/var/lib/mysql
fi

# Запускаем MariaDB через сервис (он сам дождется инициализации)
service mariadb start

# На всякий случай ждем, пока сервер не начнет отвечать
while ! mysqladmin ping --silent; do
    sleep 1
done

# Создаем базу и пользователя
mysql -u root -e "CREATE DATABASE IF NOT EXISTS gdbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "CREATE USER IF NOT EXISTS 'bot'@'localhost' IDENTIFIED BY 'botpassword';"
mysql -u root -e "GRANT ALL PRIVILEGES ON gdbot.* TO 'bot'@'localhost';"
mysql -u root -e "FLUSH PRIVILEGES;"

# Запускаем бота в активном режиме
cd /app
python main.py
