import asyncio
import os
import sqlite3
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder


# =========================================================
# НАСТРОЙКИ
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("Не указан BOT_TOKEN")

START_BALANCE = 1000
MIN_BET = 10
MAX_BET = 1_000_000

DB_NAME = "casino.db"


# =========================================================
# TELEGRAM
# =========================================================

bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(DB_NAME)
db.row_factory = sqlite3.Row


def init_db():
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 1000,
            games INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            draws INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bet INTEGER NOT NULL,
            player_cards TEXT NOT NULL,
            dealer_cards TEXT NOT NULL,
            result TEXT NOT NULL,
            profit INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    db.commit()


def get_user(user_id, username="", first_name=""):
    cursor = db.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    )

    user = cursor.fetchone()

    if user is None:
        cursor.execute("""
            INSERT INTO users
            (user_id, username, first_name, balance)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            START_BALANCE
        ))

        db.commit()

        cursor.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )

        user = cursor.fetchone()

    else:
        cursor.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
        """, (
            username,
            first_name,
            user_id
        ))

        db.commit()

    return user


def update_balance(user_id, amount):
    db.execute("""
        UPDATE users
        SET balance = balance + ?,
            profit = profit + ?
        WHERE user_id = ?
    """, (
        amount,
        amount,
        user_id
    ))

    db.commit()


def save_game(
    user_id,
    bet,
    player_cards,
    dealer_cards,
    result,
    profit
):
    db.execute("""
        INSERT INTO game_history
        (
            user_id,
            bet,
            player_cards,
            dealer_cards,
            result,
            profit,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        bet,
        player_cards,
        dealer_cards,
        result,
        profit,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    db.commit()


def increment_stat(user_id, result):
    if result == "win":
        column = "wins"
    elif result == "loss":
        column = "losses"
    else:
        column = "draws"

    db.execute(
        f"""
        UPDATE users
        SET games = games + 1,
            {column} = {column} + 1
        WHERE user_id = ?
        """,
        (user_id,)
    )

    db.commit()


# =========================================================
# CARDS
# =========================================================

SUITS = ["♠️", "♥️", "♦️", "♣️"]

RANKS = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
    "A": 11,
}


def create_deck():
    deck = []

    for suit in SUITS:
        for rank in RANKS:
            deck.append((rank, suit))

    random.shuffle(deck)

    return deck


def card_text(card):
    rank, suit = card
    return f"{rank}{suit}"


def hand_text(hand):
    return " ".join(card_text(card) for card in hand)


def calculate_score(hand):
    score = sum(RANKS[rank] for rank, suit in hand)

    aces = sum(
        1
        for rank, suit in hand
        if rank == "A"
    )

    while score > 21 and aces > 0:
        score -= 10
        aces -= 1

    return score


def is_blackjack(hand):
    return (
        len(hand) == 2
        and calculate_score(hand) == 21
    )


# =========================================================
# ACTIVE GAMES
# =========================================================

games = {}


# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🃏 Играть",
        callback_data="new_game"
    )

    builder.button(
        text="💰 Баланс",
        callback_data="show_balance"
    )

    builder.button(
        text="🏆 Рейтинг",
        callback_data="rating"
    )

    builder.adjust(1)

    return builder.as_markup()


def game_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🃏 Ещё",
        callback_data="hit"
    )

    builder.button(
        text="✋ Стоп",
        callback_data="stand"
    )

    builder.adjust(2)

    return builder.as_markup()


def new_game_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🎰 Новая игра",
        callback_data="new_game"
    )

    builder.button(
        text="💰 Баланс",
        callback_data="show_balance"
    )

    builder.adjust(1)

    return builder.as_markup()


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):

    get_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    await message.answer(
        "🎰 <b>Добро пожаловать в виртуальное казино!</b>\n\n"
        f"💰 Твой стартовый баланс: <b>{START_BALANCE:,}</b>\n\n"
        "🃏 Доступные команды:\n"
        "/balance — баланс\n"
        "/deposit 1000 — получить виртуальные деньги\n"
        "/withdraw 500 — снять виртуальные деньги\n"
        "/history — история игр\n"
        "/rating — рейтинг игроков\n"
        "/play 100 — начать Blackjack со ставкой 100\n\n"
        "Удачи! 🍀",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =========================================================
# BALANCE
# =========================================================

@dp.message(Command("balance"))
async def balance(message: Message):

    user = get_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    await message.answer(
        f"💰 <b>Твой баланс</b>\n\n"
        f"💵 {user['balance']:,} виртуальных монет\n\n"
        f"🎮 Игр: {user['games']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"💀 Поражений: {user['losses']}\n"
        f"🤝 Ничьих: {user['draws']}\n"
        f"📈 Прибыль: {user['profit']:+,}",
        parse_mode="HTML"
    )


# =========================================================
# DEPOSIT
# =========================================================

@dp.message(Command("deposit"))
async def deposit(message: Message):

    get_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    parts = message.text.split()

    if len(parts) != 2:
        await message.answer(
            "❌ Использование:\n"
            "<code>/deposit 1000</code>",
            parse_mode="HTML"
        )
        return

    try:
        amount = int(parts[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом.")
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля.")
        return

    if amount > 10_000_000:
        await message.answer(
            "❌ Максимальное пополнение: 10 000 000."
        )
        return

    update_balance(
        message.from_user.id,
        amount
    )

    user = get_user(message.from_user.id)

    await message.answer(
        f"💵 На виртуальный баланс начислено: "
        f"<b>+{amount:,}</b>\n\n"
        f"💰 Новый баланс: <b>{user['balance']:,}</b>",
        parse_mode="HTML"
    )


# =========================================================
# WITHDRAW
# =========================================================

@dp.message(Command("withdraw"))
async def withdraw(message: Message):

    user = get_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    parts = message.text.split()

    if len(parts) != 2:
        await message.answer(
            "❌ Использование:\n"
            "<code>/withdraw 500</code>",
            parse_mode="HTML"
        )
        return

    try:
        amount = int(parts[1])
    except ValueError:
        await message.answer("❌ Сумма должна быть числом.")
        return

    if amount <= 0:
        await message.answer(
            "❌ Сумма должна быть больше нуля."
        )
        return

    if amount > user["balance"]:
        await message.answer(
            "❌ Недостаточно средств.\n\n"
            f"Твой баланс: <b>{user['balance']:,}</b>",
            parse_mode="HTML"
        )
        return

    update_balance(
        message.from_user.id,
        -amount
    )

    user = get_user(message.from_user.id)

    await message.answer(
        f"💸 Списано: <b>{amount:,}</b>\n\n"
        f"💰 Новый баланс: <b>{user['balance']:,}</b>",
        parse_mode="HTML"
    )


# =========================================================
# PLAY COMMAND
# =========================================================

@dp.message(Command("play"))
async def play_command(message: Message):

    parts = message.text.split()

    if len(parts) != 2:
        await message.answer(
            "❌ Укажи ставку:\n"
            "<code>/play 100</code>",
            parse_mode="HTML"
        )
        return

    try:
        bet = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ Ставка должна быть числом."
        )
        return

    await start_blackjack(
        message,
        bet
    )


# =========================================================
# NEW GAME BUTTON
# =========================================================

@dp.callback_query(F.data == "new_game")
async def new_game(callback: CallbackQuery):

    user = get_user(
        callback.from_user.id,
        callback.from_user.username or "",
        callback.from_user.first_name or ""
    )

    await callback.message.answer(
        f"💰 Твой баланс: <b>{user['balance']:,}</b>\n\n"
        f"Минимальная ставка: <b>{MIN_BET}</b>\n"
        f"Максимальная ставка: <b>{MAX_BET:,}</b>\n\n"
        "Для игры напиши:\n"
        "<code>/play 100</code>",
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# START BLACKJACK
# =========================================================

async def start_blackjack(message, bet):

    user_id = message.from_user.id

    user = get_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    if user_id in games:
        await message.answer(
            "⚠️ У тебя уже есть активная игра."
        )
        return

    if bet < MIN_BET:
        await message.answer(
            f"❌ Минимальная ставка: <b>{MIN_BET}</b>",
            parse_mode="HTML"
        )
        return

    if bet > MAX_BET:
        await message.answer(
            f"❌ Максимальная ставка: "
            f"<b>{MAX_BET:,}</b>",
            parse_mode="HTML"
        )
        return

    if bet > user["balance"]:
        await message.answer(
            "❌ Недостаточно средств.\n\n"
            f"Баланс: <b>{user['balance']:,}</b>",
            parse_mode="HTML"
        )
        return

    # Списываем ставку
    update_balance(
        user_id,
        -bet
    )

    deck = create_deck()

    player = [
        deck.pop(),
        deck.pop()
    ]

    dealer = [
        deck.pop(),
        deck.pop()
    ]

    games[user_id] = {
        "deck": deck,
        "player": player,
        "dealer": dealer,
        "bet": bet
    }

    # BLACKJACK
    if is_blackjack(player):

        if is_blackjack(dealer):

            # Возвращаем ставку
            update_balance(user_id, bet)

            result = "draw"
            profit = 0

            increment_stat(
                user_id,
                result
            )

            save_game(
                user_id,
                bet,
                hand_text(player),
                hand_text(dealer),
                result,
                profit
            )

            games.pop(user_id, None)

            await message.answer(
                f"🃏 <b>BLACKJACK!</b>\n\n"
                f"Твои карты: {hand_text(player)}\n"
                f"Дилер: {hand_text(dealer)}\n\n"
                "🤝 У обоих Blackjack.\n"
                "Ставка возвращена.",
                parse_mode="HTML",
                reply_markup=new_game_keyboard()
            )

            return

        else:

            # Blackjack выплачивается 3:2
            payout = bet + int(bet * 1.5)

            update_balance(
                user_id,
                payout
            )

            profit = int(bet * 1.5)

            result = "win"

            increment_stat(
                user_id,
                result
            )

            save_game(
                user_id,
                bet,
                hand_text(player),
                hand_text(dealer),
                result,
                profit
            )

            games.pop(user_id, None)

            await message.answer(
                f"🃏 <b>BLACKJACK!</b> 🎉\n\n"
                f"Твои карты: {hand_text(player)}\n"
                f"Дилер: {hand_text(dealer)}\n\n"
                f"💰 Выигрыш: <b>+{profit:,}</b>",
                parse_mode="HTML",
                reply_markup=new_game_keyboard()
            )

            return

    await message.answer(
        f"🃏 <b>BLACKJACK</b>\n\n"
        f"💰 Ставка: <b>{bet:,}</b>\n\n"
        f"Твои карты:\n"
        f"{hand_text(player)}\n"
        f"Очки: <b>{calculate_score(player)}</b>\n\n"
        f"🎩 Дилер:\n"
        f"{card_text(dealer[0])} ❓\n\n"
        "Твой ход:",
        parse_mode="HTML",
        reply_markup=game_keyboard()
    )


# =========================================================
# HIT
# =========================================================

@dp.callback_query(F.data == "hit")
async def hit(callback: CallbackQuery):

    user_id = callback.from_user.id

    if user_id not in games:
        await callback.answer(
            "Активной игры нет."
        )
        return

    game = games[user_id]

    game["player"].append(
        game["deck"].pop()
    )

    score = calculate_score(
        game["player"]
    )

    # ПЕРЕБОР
    if score > 21:

        bet = game["bet"]

        result = "loss"
        profit = -bet

        increment_stat(
            user_id,
            result
        )

        save_game(
            user_id,
            bet,
            hand_text(game["player"]),
            hand_text(game["dealer"]),
            result,
            profit
        )

        games.pop(user_id, None)

        user = get_user(user_id)

        await callback.message.edit_text(
            f"💥 <b>ПЕРЕБОР!</b>\n\n"
            f"Твои карты:\n"
            f"{hand_text(game['player'])}\n"
            f"Очки: <b>{score}</b>\n\n"
            f"💸 Ты проиграл: <b>-{bet:,}</b>\n\n"
            f"💰 Баланс: <b>{user['balance']:,}</b>",
            parse_mode="HTML",
            reply_markup=new_game_keyboard()
        )

        await callback.answer()
        return

    # 21 автоматически передаем ход дилеру
    if score == 21:

        await finish_game(
            callback,
            game
        )

        games.pop(user_id, None)

        await callback.answer()
        return

    await callback.message.edit_text(
        f"🃏 <b>BLACKJACK</b>\n\n"
        f"💰 Ставка: <b>{game['bet']:,}</b>\n\n"
        f"Твои карты:\n"
        f"{hand_text(game['player'])}\n"
        f"Очки: <b>{score}</b>\n\n"
        f"🎩 Дилер:\n"
        f"{card_text(game['dealer'][0])} ❓\n\n"
        "Твой ход:",
        parse_mode="HTML",
        reply_markup=game_keyboard()
    )

    await callback.answer()


# =========================================================
# STAND
# =========================================================

@dp.callback_query(F.data == "stand")
async def stand(callback: CallbackQuery):

    user_id = callback.from_user.id

    if user_id not in games:
        await callback.answer(
            "Активной игры нет."
        )
        return

    game = games[user_id]

    await finish_game(
        callback,
        game
    )

    games.pop(user_id, None)

    await callback.answer()


# =========================================================
# FINISH GAME
# =========================================================

async def finish_game(callback, game):

    user_id = callback.from_user.id

    player = game["player"]
    dealer = game["dealer"]
    deck = game["deck"]
    bet = game["bet"]

    # Дилер берет карты до 17
    while calculate_score(dealer) < 17:
        dealer.append(
            deck.pop()
        )

    player_score = calculate_score(player)
    dealer_score = calculate_score(dealer)

    # =====================================
    # РЕЗУЛЬТАТ
    # =====================================

    if dealer_score > 21:

        result = "win"
        profit = bet

        # Возврат ставки + выигрыш
        update_balance(
            user_id,
            bet * 2
        )

        result_text = (
            "🎉 <b>Ты победил!</b>\n"
            "У дилера перебор."
        )

    elif player_score > dealer_score:

        result = "win"
        profit = bet

        update_balance(
            user_id,
            bet * 2
        )

        result_text = "🎉 <b>Ты победил!</b>"

    elif player_score < dealer_score:

        result = "loss"
        profit = -bet

        result_text = "😔 <b>Дилер победил.</b>"

    else:

        result = "draw"
        profit = 0

        # Возвращаем ставку
        update_balance(
            user_id,
            bet
        )

        result_text = "🤝 <b>Ничья!</b>"

    increment_stat(
        user_id,
        result
    )

    save_game(
        user_id,
        bet,
        hand_text(player),
        hand_text(dealer),
        result,
        profit
    )

    user = get_user(user_id)

    await callback.message.edit_text(
        f"🃏 <b>РЕЗУЛЬТАТ</b>\n\n"
        f"Твои карты:\n"
        f"{hand_text(player)}\n"
        f"💰 Очки: <b>{player_score}</b>\n\n"
        f"🎩 Карты дилера:\n"
        f"{hand_text(dealer)}\n"
        f"💰 Очки: <b>{dealer_score}</b>\n\n"
        f"{result_text}\n\n"
        f"💵 Результат ставки: "
        f"<b>{profit:+,}</b>\n"
        f"💰 Баланс: <b>{user['balance']:,}</b>",
        parse_mode="HTML",
        reply_markup=new_game_keyboard()
    )


# =========================================================
# HISTORY
# =========================================================

@dp.message(Command("history"))
async def history(message: Message):

    user_id = message.from_user.id

    get_user(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    cursor = db.cursor()

    cursor.execute("""
        SELECT *
        FROM game_history
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (user_id,))

    games_history = cursor.fetchall()

    if not games_history:

        await message.answer(
            "📜 История игр пуста."
        )

        return

    text = "📜 <b>Последние 10 игр</b>\n\n"

    icons = {
        "win": "🟢",
        "loss": "🔴",
        "draw": "🟡"
    }

    names = {
        "win": "Победа",
        "loss": "Поражение",
        "draw": "Ничья"
    }

    for game in games_history:

        icon = icons[game["result"]]
        name = names[game["result"]]

        text += (
            f"{icon} <b>{name}</b>\n"
            f"💰 Ставка: {game['bet']:,}\n"
            f"📈 Результат: {game['profit']:+,}\n"
            f"🕐 {game['created_at']}\n\n"
        )

    await message.answer(
        text,
        parse_mode="HTML"
    )


# =========================================================
# RATING
# =========================================================

@dp.message(Command("rating"))
async def rating(message: Message):

    cursor = db.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        ORDER BY balance DESC
        LIMIT 10
    """)

    users = cursor.fetchall()

    if not users:
        await message.answer(
            "🏆 Рейтинг пока пуст."
        )
        return

    text = "🏆 <b>ТОП-10 ИГРОКОВ</b>\n\n"

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    for index, user in enumerate(users):

        if index < 3:
            medal = medals[index]
        else:
            medal = f"{index + 1}."

        name = (
            f"@{user['username']}"
            if user["username"]
            else user["first_name"] or "Игрок"
        )

        text += (
            f"{medal} <b>{name}</b>\n"
            f"💰 {user['balance']:,}\n"
            f"🎮 Игр: {user['games']}\n\n"
        )

    await message.answer(
        text,
        parse_mode="HTML"
    )


# =========================================================
# BALANCE BUTTON
# =========================================================

@dp.callback_query(F.data == "show_balance")
async def balance_button(callback: CallbackQuery):

    user = get_user(
        callback.from_user.id,
        callback.from_user.username or "",
        callback.from_user.first_name or ""
    )

    await callback.message.answer(
        f"💰 <b>Твой баланс:</b> "
        f"{user['balance']:,}",
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# RATING BUTTON
# =========================================================

@dp.callback_query(F.data == "rating")
async def rating_button(callback: CallbackQuery):

    cursor = db.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        ORDER BY balance DESC
        LIMIT 10
    """)

    users = cursor.fetchall()

    text = "🏆 <b>ТОП-10</b>\n\n"

    for index, user in enumerate(users):

        if index == 0:
            medal = "🥇"
        elif index == 1:
            medal = "🥈"
        elif index == 2:
            medal = "🥉"
        else:
            medal = f"{index + 1}."

        name = (
            f"@{user['username']}"
            if user["username"]
            else user["first_name"] or "Игрок"
        )

        text += (
            f"{medal} {name} — "
            f"<b>{user['balance']:,}</b>\n"
        )

    await callback.message.answer(
        text,
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# RUN
# =========================================================

async def main():

    init_db()

    print("🎰 Casino bot started!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
  # =========================================================
# ПРОСМОТР ВСЕХ СТАВОК — ТОЛЬКО ДЛЯ АДМИНА
# =========================================================

@dp.message(Command("allbets"))
async def all_bets(message: Message):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer(
            "⛔ У тебя нет доступа к этой команде."
        )
        return

    cursor = db.cursor()

    cursor.execute("""
        SELECT
            game_history.*,
            users.username,
            users.first_name
        FROM game_history
        LEFT JOIN users
            ON game_history.user_id = users.user_id
        ORDER BY game_history.id DESC
        LIMIT 50
    """)

    bets = cursor.fetchall()

    if not bets:
        await message.answer(
            "📊 Ставок пока нет."
        )
        return

    text = "📊 <b>ПОСЛЕДНИЕ 50 СТАВОК</b>\n\n"

    for bet in bets:

        if bet["username"]:
            username = f"@{bet['username']}"
        else:
            username = bet["first_name"] or "Игрок"

        if bet["result"] == "win":
            result = "🟢 Победа"
        elif bet["result"] == "loss":
            result = "🔴 Поражение"
        else:
            result = "🟡 Ничья"

        text += (
            f"👤 <b>{username}</b>\n"
            f"🆔 ID: <code>{bet['user_id']}</code>\n"
            f"💰 Ставка: <b>{bet['bet']:,}</b>\n"
            f"{result}\n"
            f"📈 Результат: <b>{bet['profit']:+,}</b>\n"
            f"🕐 {bet['created_at']}\n"
            f"━━━━━━━━━━━━━━\n"
        )

    # Telegram имеет ограничение на длину сообщения,
    # поэтому разбиваем большой текст на части.
    max_length = 4000

    for i in range(0, len(text), max_length):
        await message.answer(
            text[i:i + max_length],
            parse_mode="HTML"
        )
