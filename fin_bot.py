import os
import logging
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler, 
    MessageHandler, filters, ConversationHandler
)

# --- КОНСТАНТЫ И НАСТРОЙКИ ---

# Токен теперь берется из переменной окружения Render
# !!! Убедитесь, что вы добавили BOT_TOKEN в настройки Render !!!
BOT_TOKEN = os.environ.get("BOT_TOKEN") 

# Константы для метода 7 конвертов
ENVELOPES_CONFIG = {
    "НЕОБХОДИМЫЕ РАСХОДЫ (55%)": 0.55,
    "ДОЛГОСРОЧНЫЕ ПОКУПКИ (10%)": 0.10,
    "ОБРАЗОВАНИЕ (10%)": 0.10,
    "ИНВЕСТИЦИИ (10%)": 0.10,
    "РАЗВЛЕЧЕНИЯ (10%)": 0.10,
    "ПОДАРКИ/БЛАГОТВОРИТЕЛЬНОСТЬ (5%)": 0.05,
    "РЕЗЕРВ (0%)": 0.00,
}
ENVELOPE_NAMES = list(name.split(' (')[0] for name in ENVELOPES_CONFIG.keys()) 

# Главные кнопки
MAIN_MENU_BUTTONS = [
    ["💰 Начать распределение", "✉️ Мои конверты"],
    ["❓ FAQ", "👤 Связаться с админом"],
]

# Ключи для состояний ConversationHandler "Начать распределение"
INPUT_INCOME, CHOOSE_OPTION, MANUAL_DISTRIBUTION = range(3)

# Ключи для состояний ConversationHandler "Мои конверты"
ENVELOPE_MENU, ENVELOPE_ACTION, ENVELOPE_INPUT = range(10, 13)

# Установка логирования (будет выводить данные в лог Render)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__) # <-- ИСПРАВЛЕНО: __name__

# --- ОБРАБОТЧИКИ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение и главное меню."""
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_BUTTONS, resize_keyboard=True, one_time_keyboard=False)
    
    welcome_text = (
        "👋 **Добро пожаловать в бот '7 Конвертов'!**\n\n"
        "Я помогу вам эффективно распределить ваш доход..."
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    return ConversationHandler.END 

async def handle_faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет ответ на FAQ."""
    faq_text = "**❓ Часто задаваемые вопросы (FAQ)**\n\n..."
    await update.message.reply_text(faq_text, parse_mode='Markdown')

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение о связи с админом."""
    admin_text = "**👤 Связь с администратором**\n\n..."
    await update.message.reply_text(admin_text, parse_mode='Markdown')

# --- ЛОГИКА РАСПРЕДЕЛЕНИЯ (ConversationHandler) ---

async def start_distribution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отлично! Напишите, пожалуйста, **общую сумму вашего дохода** (только число).")
    return INPUT_INCOME 

async def input_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает сумму дохода, рассчитывает распределение и предлагает его пользователю."""
    try:
        income = float(update.message.text.replace(',', '.'))
        if income <= 0:
            raise ValueError # <-- ИСПРАВЛЕНО: Теперь с отступом
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное положительное число.")
        return INPUT_INCOME 
        
    context.user_data['current_income'] = income
    distribution = {}
    total_check = 0
    distribution_text = "**💰 Автоматическое распределение дохода:**\n\n"
    
    for name, ratio in ENVELOPES_CONFIG.items():
        short_name = name.split(' (')[0]
        amount = round(income * ratio, 2)
        distribution[short_name] = amount
        total_check += amount
        distribution_text += f"**{short_name}:** {amount:,.2f} ₽\n"
        
    context.user_data['temp_distribution'] = distribution
    distribution_text += f"\n**Сумма для распределения:** {income:,.2f} ₽\n"
    distribution_text += f"**Распределено:** {total_check:,.2f} ₽\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Согласен, принять", callback_data="accept_distribution")],
        [InlineKeyboardButton("✏️ Ввести вручную", callback_data="manual_distribution")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(distribution_text, reply_markup=reply_markup, parse_mode='Markdown')
    return CHOOSE_OPTION 

async def handle_distribution_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор пользователя (Согласен/Изменить)."""
    query = update.callback_query
    await query.answer()

    if query.data == "accept_distribution":
        final_distribution = context.user_data.get('temp_distribution', {})
        context.user_data['my_envelopes'] = final_distribution 
        
        await query.edit_message_text("✅ **Распределение принято и сохранено!** Теперь эти суммы доступны в разделе '✉️ Мои конверты'.")
        return ConversationHandler.END 

    elif query.data == "manual_distribution":
        context.user_data['temp_distribution'] = {} 
        context.user_data['current_envelope_index'] = 0 
        first_envelope_name = ENVELOPE_NAMES[0]
        income = context.user_data['current_income']
        
        await query.edit_message_text(f"✏️ **Режим ручного ввода.**\n\n"
                                      f"Введите сумму для категории **{first_envelope_name}** (Остаток: {income:,.2f} ₽):", parse_mode='Markdown')
        return MANUAL_DISTRIBUTION 

async def handle_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает сумму для текущего конверта и переходит к следующему."""
    
    income = context.user_data['current_income']
    distribution = context.user_data.get('temp_distribution', {})
    current_index_to_save = context.user_data.get('current_envelope_index', 0)
    current_envelope_name = ENVELOPE_NAMES[current_index_to_save] 
    
    # 1. Валидация и сохранение ввода
    try:
        amount = float(update.message.text.replace(',', '.'))
        if amount < 0:
            raise ValueError("Сумма должна быть положительной.")
            
        distributed_sum = sum(distribution.values())
        remaining_income = income - distributed_sum
        
        if amount > remaining_income:
            await update.message.reply_text(f"Сумма {amount:,.2f} ₽ превышает оставшийся доход ({remaining_income:,.2f} ₽). "
                                            f"Пожалуйста, введите корректную сумму для **{current_envelope_name}**.")
            return MANUAL_DISTRIBUTION

    except ValueError:
        await update.message.reply_text(f"Пожалуйста, введите корректное число для суммы категории **{current_envelope_name}**.")
        return MANUAL_DISTRIBUTION 

    # Сохраняем введенную сумму
    distribution[current_envelope_name] = amount
    context.user_data['temp_distribution'] = distribution
    
    # Обновляем состояние для следующего конверта
    context.user_data['current_envelope_index'] = current_index_to_save + 1
    
    distributed_sum += amount
    remaining_income = income - distributed_sum
    
    # 2. Переход к следующему или завершение
    next_index = context.user_data['current_envelope_index']
    
    if next_index < len(ENVELOPE_NAMES):
        next_envelope_name = ENVELOPE_NAMES[next_index]
        await update.message.reply_text(f"✅ Сумма для **{current_envelope_name}** сохранена ({amount:,.2f} ₽).\n\n"
                                        f"Введите сумму для категории **{next_envelope_name}** (Остаток: {remaining_income:,.2f} ₽):", parse_mode='Markdown')
        return MANUAL_DISTRIBUTION 

    else:
        # Все конверты обработаны
        distribution_text = "**✅ Распределение завершено и сохранено!**\n\n"
        for name, amount in distribution.items():
            distribution_text += f"**{name}:** {amount:,.2f} ₽\n"
        
        distribution_text += f"\n**Остаток от дохода:** {remaining_income:,.2f} ₽"
        
        if 'my_envelopes' not in context.user_data:
             context.user_data['my_envelopes'] = {}
        context.user_data['my_envelopes'].update(distribution)

        await update.message.reply_text(distribution_text, parse_mode='Markdown')
        
        del context.user_data['current_income']
        del context.user_data['temp_distribution']
        del context.user_data['current_envelope_index']
        
        return ConversationHandler.END 

# --- ЛОГИКА УПРАВЛЕНИЯ КОНВЕРТАМИ (ConversationHandler) ---

async def show_envelopes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """[Состояние 10 - Вход] Показывает список конвертов в виде кнопок."""
    
    current_envelopes = context.user_data.get('my_envelopes', {k.split(' (')[0]: 0.0 for k in ENVELOPES_CONFIG})
    context.user_data['my_envelopes'] = current_envelopes

    keyboard = []
    for name, amount in current_envelopes.items():
        button_text = f"{name}: {amount:,.2f} ₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"ENVELOPE:{name}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "✉️ **Мои конверты**\n\nВыберите конверт, чтобы управлять им:", 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
    else: # Для случая, когда вызывается из другого обработчика
         await update.callback_query.edit_message_text(
            "✉️ **Мои конверты**\n\nВыберите конверт, чтобы управлять им:", 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )

    return ENVELOPE_MENU

async def show_envelopes_list_for_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Помощник для обновления сообщения с новым списком конвертов (для кнопки 'Назад')."""
    query = update.callback_query
    
    current_envelopes = context.user_data['my_envelopes']
    
    keyboard = []
    for name, amount in current_envelopes.items():
        button_text = f"{name}: {amount:,.2f} ₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"ENVELOPE:{name}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✉️ **Мои конверты**\n\nВыберите конверт, чтобы управлять им:", 
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )
    
async def select_envelope_and_show_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет выбранный конверт и показывает доступные действия."""
    query = update.callback_query
    await query.answer()
    
    envelope_name = query.data.split(":")[1]
    context.user_data['current_selected_envelope'] = envelope_name
    balance = context.user_data['my_envelopes'].get(envelope_name, 0.0)

    actions_keyboard = [
        [InlineKeyboardButton("📝 Изменить название", callback_data="ACTION:RENAME")],
        [InlineKeyboardButton("➕ Добавить деньги", callback_data="ACTION:ADD")],
        [InlineKeyboardButton("➖ Убавить деньги", callback_data="ACTION:SUBTRACT")],
        [InlineKeyboardButton("⬅️ Назад к конвертам", callback_data="ACTION:BACK_ENVELOPES")],
    ]
    reply_markup = InlineKeyboardMarkup(actions_keyboard)
    
    await query.edit_message_text(
        f"**Управление конвертом '{envelope_name}'**\n\n"
        f"Баланс: {balance:,.2f} ₽\n\n"
        "Выберите действие:", 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ENVELOPE_ACTION 

async def handle_envelope_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор действия (RENAME/ADD/SUBTRACT/BACK)."""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split(":")[1]
    envelope_name = context.user_data['current_selected_envelope']
    context.user_data['current_action'] = action

    if action == "BACK_ENVELOPES":
        await show_envelopes_list_for_callback(update, context) 
        return ENVELOPE_MENU
    
    # ... (логика для RENAME/ADD/SUBTRACT - осталось без изменений, но требует ENVELOPE_INPUT) ...
    # Так как логика одинакова, просто переходим в ENVELOPE_INPUT с соответствующим запросом:
    
    if action == "RENAME":
        await query.edit_message_text(f"📝 **Переименование конверта '{envelope_name}'**\n\n"
                                      "Введите **новое название** для этой категории:")
    elif action == "ADD":
        await query.edit_message_text(f"➕ **Пополнение конверта '{envelope_name}'**\n\n"
                                      "Введите **сумму** для добавления:")
    elif action == "SUBTRACT":
        current_amount = context.user_data['my_envelopes'].get(envelope_name, 0.0)
        await query.edit_message_text(f"➖ **Уменьшение конверта '{envelope_name}'**\n\n"
                                      f"Текущий баланс: {current_amount:,.2f} ₽\n"
                                      "Введите **сумму** для изъятия:")
        
    return ENVELOPE_INPUT
        
async def handle_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод нового значения (имя или сумма) и обновляет конверт."""
    
    action = context.user_data.get('current_action')
    old_name = context.user_data['current_selected_envelope']
    user_data_envelopes = context.user_data['my_envelopes']
    
    # ... (логика обработки ввода - осталось без изменений) ...
    success_message = f"**Операция для конверта '{old_name}' выполнена успешно!**"

    if action == "RENAME":
        new_name = update.message.text.strip()
        if not new_name:
            await update.message.reply_text("Название не может быть пустым. Попробуйте еще раз:")
            return ENVELOPE_INPUT
            
        if old_name in user_data_envelopes:
            user_data_envelopes[new_name] = user_data_envelopes.pop(old_name)
        
        success_message = f"📝 Название конверта успешно изменено с **'{old_name}'** на **'{new_name}'**."
        
    elif action in ["ADD", "SUBTRACT"]:
        try:
            value = float(update.message.text.replace(',', '.'))
            if value <= 0:
                raise ValueError("Сумма должна быть положительной.")

            current_amount = user_data_envelopes.get(old_name, 0.0)
            
            if action == "ADD":
                user_data_envelopes[old_name] = current_amount + value
                success_message = f"➕ {value:,.2f} ₽ добавлено. Новый баланс: {user_data_envelopes[old_name]:,.2f} ₽."
            
            elif action == "SUBTRACT":
                if current_amount < value:
                    await update.message.reply_text(f"Недостаточно средств. Текущий баланс: {current_amount:,.2f} ₽. Введите сумму не более текущего баланса:")
                    return ENVELOPE_INPUT
                
                user_data_envelopes[old_name] = current_amount - value
                success_message = f"➖ {value:,.2f} ₽ изъято. Новый баланс: {user_data_envelopes[old_name]:,.2f} ₽."
                
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректное число для суммы.")
            return ENVELOPE_INPUT
    
    # Очистка временных данных
    if 'current_action' in context.user_data: del context.user_data['current_action']
    if 'current_selected_envelope' in context.user_data: del context.user_data['current_selected_envelope']
    
    # Отправка сообщения об успехе и возврат в главное меню
    await update.message.reply_text(success_message, parse_mode='Markdown')
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_BUTTONS, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Выберите следующее действие в **главном меню**:", reply_markup=reply_markup, parse_mode='Markdown')
    
    return ConversationHandler.END 

# --- ФУНКЦИЯ ДЛЯ СБОРКИ APPLICATION (ВАЖНО ДЛЯ WEBHOOK) ---

def build_application() -> Application:
    """Собирает и возвращает объект Application с настроенными обработчиками."""
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в переменных окружения.")
        raise ValueError("BOT_TOKEN is not set.")

    # 1. Создаем приложение (Updater=None для Webhook)
    application = Application.builder().token(BOT_TOKEN).updater(None).build()
    
    # 2. ConversationHandler для "Начать распределение"
    distribution_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Начать распределение$"), start_distribution)],
        states={
            INPUT_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_income)],
            CHOOSE_OPTION: [CallbackQueryHandler(handle_distribution_choice)],
            MANUAL_DISTRIBUTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_input)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    # 3. ConversationHandler для "Мои конверты" (управление конвертами)
    envelope_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✉️ Мои конверты$"), show_envelopes)],
        states={
            ENVELOPE_MENU: [CallbackQueryHandler(select_envelope_and_show_actions, pattern="^ENVELOPE:")],
            ENVELOPE_ACTION: [CallbackQueryHandler(handle_envelope_action, pattern="^ACTION:")],
            ENVELOPE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_value_input)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # 4. Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^❓ FAQ$"), handle_faq))
    application.add_handler(MessageHandler(filters.Regex("^👤 Связаться с админом$"), handle_admin))
    application.add_handler(distribution_handler)
    application.add_handler(envelope_handler)

    return application

# --- ЗАПУСК ПОЛЛИНГОМ (УДАЛЕНО) ---
# Блок if __name__ == "__main__": main() УДАЛЕН.
# Запуск будет осуществляться из app.py