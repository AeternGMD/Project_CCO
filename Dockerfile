FROM python:3.11-slim

# Установка клиента MySQL для бэкапов (mysqldump)
RUN apt-get update && \
    apt-get install -y default-mysql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота
COPY . .

# Запуск бота напрямую
CMD ["python", "main.py"]
