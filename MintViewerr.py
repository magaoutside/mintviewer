import asyncio
import aiohttp
import aiosqlite
import logging
import socketio
from datetime import datetime
from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

DB_PATH = "subscriptions.db"

paid_subscriptions = set()
active_notifications = set()

CHANNEL_USERNAME = "@Nftsgiftsnews"
EXTRA_CHANNEL = "@shapodev"

GIFT_ORDER = [
    "Neko Helmet", "Candy Cane", "Tama Gadget", "Electric Skull", "Snow Globe",
    "Winter Wreath", "Record Player", "Top Hat", "Sleigh Bell", "Sakura Flower",
    "Diamond Ring", "Toy Bear", "Love Potion", "Loot Bag", "Star Notepad",
    "Ion Gem", "Lol Pop", "Mini Oscar", "Ginger Cookie", "Swiss Watch",
    "Eternal Candle", "Crystal Ball", "Flying Broom", "Astral Shard", "Bunny Muffin",
    "B-Day Candle", "Hypno Lollipop", "Mad Pumpkin", "Voodoo Doll", "Snow Mittens",
    "Jingle Bells", "Desk Calendar", "Cookie Heart", "Love Candle", "Hanging Star",
    "Witch Hat", "Jester Hat", "Party Sparkler", "Lunar Snake", "Genie Lamp",
    "Homemade Cake", "Spy Agaric", "Scared Cat", "Skull Flower", "Trapped Heart",
    "Sharp Tongue", "Evil Eye", "Hex Pot", "Kissed Frog", "Magic Potion",
    "Vintage Cigar", "Berry Box", "Eternal Rose", "Perfume Bottle", "Durov's Cap",
    "Jelly Bunny", "Spiced Wine", "Plush Pepe", "Precious Peach", "Signet Ring", "Santa Hat"
]
ALLOWED_GIFTS = set(g.replace(" ", "").lower() for g in GIFT_ORDER)

user_gift_filters = {}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS subscriptions (chat_id INTEGER PRIMARY KEY, subscription_date TEXT)"
        )
        await db.commit()
        async with db.execute("SELECT chat_id FROM subscriptions") as cursor:
            async for row in cursor:
                paid_subscriptions.add(row[0])
    logger.info("Загружены оплаченные подписки: %s", paid_subscriptions)

async def add_subscription(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions (chat_id, subscription_date) VALUES (?, ?)",
            (chat_id, datetime.utcnow().isoformat())
        )
        await db.commit()
    paid_subscriptions.add(chat_id)
    logger.info("Добавлена подписка для чата %s", chat_id)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        member1 = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=update.effective_user.id)
        member2 = await context.bot.get_chat_member(chat_id=EXTRA_CHANNEL, user_id=update.effective_user.id)
        if member1.status in ["left", "kicked"] or member2.status in ["left", "kicked"]:
            await update.message.reply_text(
                "❗ Внимание!\n"
                "Чтобы получать уведомления, подпишитесь на каналы:\n"
                f"{CHANNEL_USERNAME} и {EXTRA_CHANNEL}.\n\n"
                "После подписки повторите команду /start."
            )
            return
    except Exception as e:
        logger.error("Ошибка проверки членства: %s", e)
        await update.message.reply_text("Не удалось проверить подписку на каналы. Попробуйте позже.")
        return

    if chat_id in paid_subscriptions:
        active_notifications.add(chat_id)
        await update.message.reply_text(
            "✅ Уведомления успешно включены!\n"
            "Вы будете своевременно получать все обновления."
        )
    else:
        await update.message.reply_text(
            "ℹ️ У вас отсутствует активная подписка.\n"
            "Для активации подписки используйте команду /buy."
        )

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_notifications:
        active_notifications.remove(chat_id)
        await update.message.reply_text(
            "🛑 Уведомления отключены.\n"
            "Вы можете включить их снова, используя команду /start."
        )
    else:
        await update.message.reply_text("Уведомления уже отключены.")

async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in paid_subscriptions:
        await update.message.reply_text(
            "✅ Подписка уже активна.\n"
            "Благодарим за использование сервиса!"
        )
        return

    title = "Подписка на уведомления"
    description = (
        "Подписка на уведомления о новинках подарков.\n"
        "Стоимость: 15 звезд."
    )
    payload = "subscription_payload"
    provider_token = ""
    currency = "XTR"
    prices = [LabeledPrice("Подписка (15 звезд)", 15)]
    start_parameter = "subscription"

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=provider_token,
        currency=currency,
        prices=prices,
        start_parameter=start_parameter,
    )

async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Использование: /filter Plush Pepe, Cookie Heart, ...(Можно писать как Plush Pepe, так и PlushPepe)")
        return
    gifts_str = " ".join(context.args)
    gift_list = [gift.strip() for gift in gifts_str.split(",") if gift.strip()]
    processed_gifts = [gift.replace(" ", "").lower() for gift in gift_list]
    invalid_gifts = [gift for gift in gift_list if gift.replace(" ", "").lower() not in ALLOWED_GIFTS]
    if invalid_gifts:
        await update.message.reply_text("Следующие подарки не существуют: " + ", ".join(invalid_gifts))
        return
    user_gift_filters[chat_id] = set(processed_gifts)
    await update.message.reply_text("Фильтр уведомлений установлен:\n" + ", ".join(gift_list))

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_gift_filters:
        del user_gift_filters[chat_id]
        await update.message.reply_text(
            "✅ Фильтр уведомлений очищен.\n"
            "Теперь вы будете получать уведомления по всем подаркам."
        )
    else:
        await update.message.reply_text("Фильтр уведомлений не был установлен.")

async def gifts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gift_list_text = "\n".join(GIFT_ORDER)
    await update.message.reply_text("Список подарков:\n" + gift_list_text)

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload != 'subscription_payload':
        await query.answer(ok=False, error_message="Что-то пошло не так...")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await add_subscription(chat_id)
    active_notifications.add(chat_id)
    await update.message.reply_text(
        "✅ Платеж успешно выполнен!\n"
        "Уведомления активированы. Благодарим за покупку!"
    )

def create_socketio_client():
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)
    sio = socketio.AsyncClient(
        http_session=session,
        logger=True,
        engineio_logger=True,
        reconnection=False
    )
    return sio

async def main():
    global application

    await init_db()

    bot_token = "your_token"
    application = ApplicationBuilder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("stop", stop_cmd))
    application.add_handler(CommandHandler("buy", buy_cmd))
    application.add_handler(CommandHandler("filter", filter_command))
    application.add_handler(CommandHandler("clear", clear_cmd))
    application.add_handler(CommandHandler("gifts", gifts_cmd))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    sio = create_socketio_client()

    @sio.event
    async def connect():
        logger.info("Подключение к Socket.IO серверу установлено.")

    @sio.event
    async def disconnect():
        logger.info("Отключение от Socket.IO сервера.")

    @sio.on("*")
    async def catch_all(event, data):
        logger.info("Получено событие '%s' с данными: %s", event, data)
        payload = None
        if isinstance(data, list) and len(data) >= 2:
            payload = data[1]
        elif isinstance(data, dict):
            payload = data
        if payload and payload.get("type") == "newMint":
            slug = payload.get("slug", "")
            owner = payload.get("owner", {})
            owner_name = owner.get("name", "")
            gift_name = payload.get("gift_name", "")
            gift_name_processed = gift_name.replace(" ", "").lower()
            for chat_id in list(active_notifications):
                user_filter = user_gift_filters.get(chat_id)
                if user_filter is not None and user_filter:
                    if not any(filter_word in gift_name_processed for filter_word in user_filter):
                        continue
                message_text = (
                    "🔔 Новое уведомление!\n"
                    f"Ссылка: http://t.me/nft/{slug}\n"
                    f"От: {owner_name}"
                )
                logger.info("Формирование уведомления: %s", message_text)
                try:
                    member1 = await application.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=chat_id)
                    member2 = await application.bot.get_chat_member(chat_id=EXTRA_CHANNEL, user_id=chat_id)
                    if member1.status in ["left", "kicked"] or member2.status in ["left", "kicked"]:
                        active_notifications.remove(chat_id)
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=("Вы отписаны от одного из обязательных каналов "
                                    f"({CHANNEL_USERNAME} или {EXTRA_CHANNEL}).\n"
                                    "Подпишитесь, чтобы продолжить получать уведомления.")
                        )
                        continue
                    await application.bot.send_message(chat_id=chat_id, text=message_text)
                    logger.info("Сообщение отправлено в чат %s", chat_id)
                except Exception as e:
                    logger.error("Ошибка отправки сообщения в чат %s: %s", chat_id, e)

    async def start_socketio():
        url = "https://gsocket.trump.tg"
        base_delay = 2
        max_delay = 60
        delay = base_delay
        while True:
            try:
                logger.info("Попытка подключения к %s...", url)
                await sio.connect(url)
                logger.info("Подключение выполнено, ожидание событий...")
                delay = base_delay
                await sio.wait()
            except Exception as e:
                logger.error("Ошибка подключения к Socket.IO серверу: %s", e)
                logger.info("Повторное подключение через %d секунд...", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    asyncio.create_task(start_socketio())

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
