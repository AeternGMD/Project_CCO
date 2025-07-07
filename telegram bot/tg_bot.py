from BOT_API import API
help_message = open('telegram bot\\help_message.txt', encoding='UTF-8').read()
from telebot import TeleBot, types
BOT_API = API

bot = TeleBot(token=BOT_API)

@bot.message_handler(commands=['help'])
def send_help_message(message):
    bot.send_message(
        chat_id=message.chat.id,
        text=help_message # type: ignore
    )

@bot.message_handler()
def send_echo(message: types.Message):
    bot.send_message(
        chat_id=message.chat.id,
        text=message.text # type: ignore
    )

bot.infinity_polling(skip_pending=True)