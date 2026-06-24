import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# Твой рабочий токен (на Render из Германии он заведется напрямую)
bot_token = "8966417281:AAEJpg850s0UcttIeUyu7HcN3wFte4ruSFg"

bot = Bot(token=bot_token)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📱 Создать фильтр", callback_data="create_filter"),
        types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 Статистика цен", callback_data="stats"),
        types.InlineKeyboardButton(text="🔥 Топ сделок", callback_data="top_deals")
    )
    await message.answer(
        "👋 **Монитор Авито успешно запущен на бесплатном облаке!**\n\n"
        "Связь идеальная. Используй меню ниже:",
        reply_markup=builder.as_markup()
    )

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
