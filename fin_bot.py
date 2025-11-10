import os
import logging
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler, 
    MessageHandler, filters, ConversationHandler
)

# --- КОНСТАНТЫ И НАСТРОЙКИ ---

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
# Использование среза строки для ENVELOPE_NAMES
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

# Установка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ГЛАВНЫЕ ОБРАБОТЧИКИ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение и главное меню."""
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_BUTTONS, resize_keyboard=True, one_time_keyboard=False)
    
    welcome_text = (
        "👋 **Добро пожаловать в бот '7 Конвертов'!**\n\n"
        "Я помогу вам эффективно распределить ваш доход..."
    )
    
    # Определяем, был ли вызов из команды /start или из fallbacks
    message_source = update.message if update.message else update.effective_message

    await message_source.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    # Сброс всех активных ConversationHandler, если пользователь явно вызвал /start
    return ConversationHandler.END 

async def handle_faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет ответ на FAQ."""
    faq_text = "**❓ Часто задаваемые вопросы (FAQ)**\n\n..."
    await update.message.reply_text(faq_text, parse_mode='Markdown')

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение о связи с админом."""
    admin_text = "**👤 Связь с администратором**\n\n..."
    await update.message.reply_text(admin_text, parse_mode='Markdown')

# --- ЛОГИКА РАСПРЕДЕЛЕНИЯ ---

async def cancel_distribution(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Централизованная очистка временных данных распределения."""
    context.user_data.pop('current_income', None)
    context.user_data.pop('temp_distribution', None)
    context.user_data.pop('current_envelope_index', None)

async def start_distribution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отлично! Напишите, пожалуйста, **общую сумму вашего дохода** (только число).")
    return INPUT_INCOME 

async def input_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает сумму дохода, рассчитывает распределение и предлагает его пользователю."""
    try:
        income = float(update.message.text.replace(',', '.'))
        if income <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное положительное число. Введите сумму еще раз:")
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
    
    # Добавление информации о проверке, чтобы пользователь знал о точности округления
    distribution_text += f"\n**Сумма для распределения:** {income:,.2f} ₽\n"
    distribution_text += f"**Распределено (с учетом округления):** {total_check:,.2f} ₽\n"
    
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
        # Инициализируем 'my_envelopes' при первом сохранении
        if 'my_envelopes' not in context.user_data:
             context.user_data['my_envelopes'] = {}
        # Обновляем или добавляем новые суммы
        context.user_data['my_envelopes'].update(final_distribution)
        
        await query.edit_message_text("✅ **Распределение принято и сохранено!** Теперь эти суммы доступны в разделе '✉️ Мои конверты'.", parse_mode='Markdown')
        await cancel_distribution(context)
        return ConversationHandler.END 

    elif query.data == "manual_distribution":
        # Начинаем ручной ввод
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
            raise ValueError

        distributed_sum = sum(distribution.values())
        remaining_income = income - distributed_sum
        
        if amount > remaining_income:
            await update.message.reply_text(f"Сумма {amount:,.2f} ₽ превышает оставшийся доход ({remaining_income:,.2f} ₽). "
                                            f"Пожалуйста, введите корректную сумму для **{current_envelope_name}**:")
            return MANUAL_DISTRIBUTION

    except ValueError:
        await update.message.reply_text(f"Пожалуйста, введите корректное положительное число для суммы категории **{current_envelope_name}**:")
        return MANUAL_DISTRIBUTION 

    # Сохраняем введенную сумму
    distribution[current_envelope_name] = amount
    context.user_data['temp_distribution'] = distribution
    
    # Обновляем состояние для следующего конверта
    next_index = current_index_to_save + 1
    context.user_data['current_envelope_index'] = next_index
    
    distributed_sum += amount
    remaining_income = income - distributed_sum
    
    # 2. Переход к следующему или завершение
    if next_index < len(ENVELOPE_NAMES):
        next_envelope_name = ENVELOPE_NAMES[next_index]
        await update.message.reply_text(f"✅ Сумма для **{current_envelope_name}** сохранена ({amount:,.2f} ₽).\n\n"
                                        f"Введите сумму для категории **{next_envelope_name}** (Остаток: {remaining_income:,.2f} ₽):", parse_mode='Markdown')
        return MANUAL_DISTRIBUTION 

    else:
        # Все конверты обработаны
        distribution_text = "**✅ Распределение завершено и сохранено!**\n\n"
        for name, amount_val in distribution.items():
            distribution_text += f"**{name}:** {amount_val:,.2f} ₽\n"
        
        distribution_text += f"\n**Остаток от дохода:** {remaining_income:,.2f} ₽"
        
        # Обновление основных конвертов
        if 'my_envelopes' not in context.user_data:
             context.user_data['my_envelopes'] = {}
        context.user_data['my_envelopes'].update(distribution)

        await update.message.reply_text(distribution_text, parse_mode='Markdown')
        
        await cancel_distribution(context)
        return ConversationHandler.END 

# --- ЛОГИКА УПРАВЛЕНИЯ КОНВЕРТАМИ ---

async def show_envelopes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает список конвертов в виде кнопок. Работает как для Message, так и для CallbackQuery."""
    
    # Инициализация конвертов, если они еще не существуют
    current_envelopes = context.user_data.get('my_envelopes', {k.split(' (')[0]: 0.0 for k in ENVELOPES_CONFIG})
    context.user_data['my_envelopes'] = current_envelopes

    keyboard = []
    for name, amount in current_envelopes.items():
        button_text = f"{name}: {amount:,.2f} ₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"ENVELOPE:{name}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "✉️ **Мои конверты**\n\nВыберите конверт, чтобы управлять им:"

    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
         await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    return ENVELOPE_MENU

# Удалена show_envelopes_list_for_callback, вместо нее используется show_envelopes (через update.callback_query)

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
        # Используем show_envelopes для возврата к списку
        return await show_envelopes(update, context) 
    
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
    
    success_message = f"**Операция для конверта '{old_name}' выполнена успешно!**"
    next_state = ConversationHandler.END # По умолчанию завершаем

    if action == "RENAME":
        new_name = update.message.text.strip()
        if not new_name:
            await update.message.reply_text("Название не может быть пустым. Попробуйте еще раз:")
            next_state = ENVELOPE_INPUT
        elif new_name in user_data_envelopes and new_name != old_name:
            await update.message.reply_text("Конверт с таким названием уже существует. Попробуйте другое название:")
            next_state = ENVELOPE_INPUT
        else:
            # Обновление ключа в словаре
            user_data_envelopes[new_name] = user_data_envelopes.pop(old_name)
            success_message = f"📝 Название конверта успешно изменено с **'{old_name}'** на **'{new_name}'**."
            context.user_data['current_selected_envelope'] = new_name # Обновляем имя
        
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
                    next_state = ENVELOPE_INPUT
                else:
                    user_data_envelopes[old_name] = current_amount - value
                    success_message = f"➖ {value:,.2f} ₽ изъято. Новый баланс: {user_data_envelopes[old_name]:,.2f} ₽."
                
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректное положительное число для суммы.")
            next_state = ENVELOPE_INPUT

    # Очистка временных данных только при успешном завершении (END)
    if next_state == ConversationHandler.END:
        context.user_data.pop('current_action', None)
        context.user_data.pop('current_selected_envelope', None)
        
        # Отправка сообщения об успехе и возврат в главное меню
        await update.message.reply_text(success_message, parse_mode='Markdown')
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU_BUTTONS, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Выберите следующее действие в **главном меню**:", reply_markup=reply_markup, parse_mode='Markdown')
        
    return next_state 

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
        # Обработка /start и других команд внутри Conversation
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
        # Обработка /start и других команд внутри Conversation
        fallbacks=[CommandHandler("start", start)],
    )

    # 4. Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^❓ FAQ$"), handle_faq))
    application.add_handler(MessageHandler(filters.Regex("^👤 Связаться с админом$"), handle_admin))
    application.add_handler(distribution_handler)
    application.add_handler(envelope_handler)
    
    # Добавление обработчика для нераспознанных текстовых сообщений
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text_handler))

    return application
