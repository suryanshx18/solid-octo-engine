from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Bot is running.")

@router.message(Command("test"))
async def cmd_test(message: Message):
    await message.answer("Handlers loaded correctly.")
