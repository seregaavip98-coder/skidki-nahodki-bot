import aiohttp
import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = os.getenv("ADMIN_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "data/bot.db")

if not TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

if not ADMIN_ID.isdigit():
    raise RuntimeError("Не задан ADMIN_ID")

ADMIN_ID = int(ADMIN_ID)

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(DB_PATH)

db.execute("""
CREATE TABLE IF NOT EXISTS subscribers (
    user_id INTEGER PRIMARY KEY,
    active INTEGER DEFAULT 1
)
""")
db.commit()

bot = Bot(token=TOKEN)
dp = Dispatcher()

waiting_for_post = set()


def admin(user_id):
    return user_id == ADMIN_ID


def subscribe(user_id, active=1):
    db.execute(
        "INSERT INTO subscribers(user_id, active) VALUES(?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET active=excluded.active",
        (user_id, active),
    )
    db.commit()


def subscribers():
    return [
        row[0] for row in
        db.execute(
            "SELECT user_id FROM subscribers WHERE active=1"
        ).fetchall()
    ]


@dp.message(CommandStart())
async def start(message: Message):
    subscribe(message.from_user.id)

    await message.answer(
        "🎁 Добро пожаловать в «Скидки и находки 24/7»!\n\n"
        "Здесь будут появляться интересные скидки, "
        "акции и выгодные предложения.\n\n"
        "/help — помощь\n"
        "/stop — отключить рассылку"
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "🤖 Скидки и находки 24/7\n\n"
        "Подписка — /start\n"
        "Отключить рассылку — /stop\n\n"
        "Сейчас публикации добавляет администратор."
    )


@dp.message(Command("stop"))
async def stop(message: Message):
    subscribe(message.from_user.id, 0)
    await message.answer("Рассылка отключена. /start — включить.")


@dp.message(Command("stats"))
async def stats(message: Message):
    if not admin(message.from_user.id):
        return

    total = db.execute(
        "SELECT COUNT(*) FROM subscribers"
    ).fetchone()[0]

    active = len(subscribers())

    await message.answer(
        f"📊 Статистика\nВсего: {total}\nАктивных: {active}"
    )


@dp.message(Command("publish"))
async def publish(message: Message):
    if not admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    waiting_for_post.add(message.from_user.id)

    await message.answer(
        "Отправь следующим сообщением текст, фото или видео скидки."
    )


@dp.message(F.from_user)
async def admin_post(message: Message):
    user_id = message.from_user.id

    if not admin(user_id) or user_id not in waiting_for_post:
        return

    waiting_for_post.discard(user_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🚀 Опубликовать",
                callback_data="publish"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel"
            )
        ]]
    )

    await message.copy_to(
        chat_id=message.chat.id,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery):
    if not admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отменено")


@dp.callback_query(F.data == "publish")
async def publish_post(callback: CallbackQuery):
    if not admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return

    sent = 0
    failed = 0

    await callback.answer("Публикуем...")

    for user_id in subscribers():
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=callback.message.chat.id,
                message_id=callback.message.message_id
            )
            sent += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.04)

    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.message.answer(
        f"✅ Рассылка завершена!\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )


async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
