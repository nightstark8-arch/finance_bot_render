import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from http import HTTPStatus
from telegram.ext import Application
from fin_bot import BOT_TOKEN # Импорт токена и Application

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Инициализация Telegram Application (без запуска) ---
# Предполагаем, что ваш finance_bot.py содержит функцию для сборки application
# Если у вас нет такой функции, инициализируйте Application здесь,
# добавив все свои хэндлеры (start_handler, input_income_handler и т.д.)

application = (
    Application.builder()
    .token(BOT_TOKEN)
    .updater(None) # Отключаем опрос
    .build()
)

# ... Здесь нужно добавить все ваши хэндлеры из finance_bot.py в application ...
# Пример: 
# from finance_bot import start_handler, distribution_handler, ...
# application.add_handler(start_handler)
# application.add_handler(distribution_handler)
# ...

# --- Инициализация FastAPI ---
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Запуск PTB application при старте сервера
    await application.initialize()
    await application.start()
    logger.info("PTB Application Started")

@app.on_event("shutdown")
async def shutdown_event():
    # Остановка PTB application при выключении сервера
    await application.stop()
    logger.info("PTB Application Stopped")


@app.post("/")
async def telegram_webhook(request: Request):
    """Принимает обновления от Telegram и передает их боту."""
    try:
        req_json = await request.json()
        update = Update.de_json(req_json, application.bot)
        
        # Передаем обновление в обработчики PTB
        await application.process_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка при обработке обновления: {e}")
        return {"status": "error"}, HTTPStatus.INTERNAL_SERVER_ERROR