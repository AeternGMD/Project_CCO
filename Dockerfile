FROM python:3.11-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Environment variables will be provided via .env file or docker run
# Create data directory for SQLite
RUN mkdir -p data

CMD ["python", "main.py"]
