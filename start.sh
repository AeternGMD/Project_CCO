#!/bin/bash
# start.sh - Script to easily start the bot on a Linux server

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed. Please install Python 3.9+ to continue."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🛠️ Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found. Creating a template..."
    echo "BOT_TOKEN=YOUR_BOT_TOKEN_HERE" > .env
    echo "CHANNEL_ID=YOUR_CHANNEL_ID_HERE" >> .env
    echo "ROOT_ID=YOUR_TELEGRAM_ID_HERE" >> .env
    echo "DB_PATH=data/database.db" >> .env
    echo "❌ Please edit the .env file with your bot token and try again."
    exit 1
fi

# Run the bot
echo "🚀 Starting the bot..."
python3 main.py
