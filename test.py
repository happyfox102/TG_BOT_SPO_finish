import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import psycopg2
from psycopg2.extras import RealDictCursor
import random
from datetime import datetime

# Конфигурация логирования
logging.basicConfig(level=logging.INFO)
bot = Bot(token='##########################')  # Замените на действительный токен
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)

# Подключение к PostgreSQL
try:
    conn = psycopg2.connect(
        dbname="team_bot_db",
        user="postgres",
        password="123",
        host="localhost",
        port="5432"
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    logging.info("Успешное подключение к базе данных")
except psycopg2.Error as e:
    logging.error(f"Ошибка подключения к базе данных: {e}")
    raise

# Создание таблиц
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        first_name VARCHAR(100),
        last_name VARCHAR(100),
        group_name VARCHAR(50),
        direction VARCHAR(100),
        skills TEXT
    );
    CREATE TABLE IF NOT EXISTS teams (
        team_id SERIAL PRIMARY KEY,
        team_name VARCHAR(100)
    );
    CREATE TABLE IF NOT EXISTS user_teams (
        user_id BIGINT,
        team_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
    );
    CREATE TABLE IF NOT EXISTS tasks (
        task_id SERIAL PRIMARY KEY,
        team_id INTEGER,
        task_text TEXT,
        is_completed BOOLEAN DEFAULT FALSE,
        assigned_at TIMESTAMP,
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
    );
""")
conn.commit()

# Список ID администраторов
ADMIN_IDS = [#################################]  # Добавьте дополнительные ID администраторов здесь

# Состояния для регистрации
class Registration(StatesGroup):
    first_name = State()
    last_name = State()
    group = State()
    direction = State()
    skills = State()

# Состояния для отправки задания
class SendTask(StatesGroup):
    task_text = State()

# Клавиатура
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Зарегистрироваться")],
            [KeyboardButton(text="Моя команда")],
            [KeyboardButton(text="Статистика")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: Message):
    logging.info(f"Получена команда /start от пользователя {message.from_user.id}")
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=get_main_menu())

# Начало регистрации
@dp.message(lambda message: message.text == "Зарегистрироваться")
async def register_start(message: Message, state: FSMContext):
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    if cursor.fetchone():
        await message.answer("Вы уже зарегистрированы!")
        return
    await state.set_state(Registration.first_name)
    await message.answer("Введите ваше имя:")

# Обработка имени
@dp.message(Registration.first_name)
async def process_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await state.set_state(Registration.last_name)
    await message.answer("Введите вашу фамилию:")

# Обработка фамилии
@dp.message(Registration.last_name)
async def process_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text)
    await state.set_state(Registration.group)
    await message.answer("Введите вашу группу:")

# Обработка группы
@dp.message(Registration.group)
async def process_group(message: Message, state: FSMContext):
    await state.update_data(group=message.text)
    await state.set_state(Registration.direction)
    await message.answer("Введите ваше направление (например, Программирование, Дизайн, Аналитика):")

# Обработка направления
@dp.message(Registration.direction)
async def process_direction(message: Message, state: FSMContext):
    await state.update_data(direction=message.text)
    await state.set_state(Registration.skills)
    await message.answer("Введите ваши навыки и качества(например, Python, Photoshop, работа в команде):")

# Завершение регистрации
@dp.message(Registration.skills)
async def process_skills(message: Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute(
        """INSERT INTO users (user_id, first_name, last_name, group_name, direction, skills)
        VALUES (%s, %s, %s, %s, %s, %s)""",
        (message.from_user.id, data['first_name'], data['last_name'],
         data['group'], data['direction'], message.text)
    )
    conn.commit()
    await state.clear()
    await message.answer("Регистрация завершена!", reply_markup=get_main_menu())

# Команда для отправки задания (для администратора)
@dp.message(Command("send_task"))
async def send_task_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для этой команды!")
        return
    await state.set_state(SendTask.task_text)
    await message.answer("Введите текст задания для всех команд:")

# Обработка текста задания
@dp.message(SendTask.task_text)
async def process_task_text(message: Message, state: FSMContext):
    task_text = message.text
    cursor.execute("SELECT team_id, team_name FROM teams")
    teams = cursor.fetchall()

    if not teams:
        await message.answer("Команды ещё не сформированы!")
        await state.clear()
        return

    for team in teams:
        cursor.execute(
            """INSERT INTO tasks (team_id, task_text, assigned_at)
            VALUES (%s, %s, %s)""",
            (team['team_id'], task_text, datetime.now())
        )
        cursor.execute(
            """SELECT u.user_id
            FROM users u
            JOIN user_teams ut ON u.user_id = ut.user_id
            WHERE ut.team_id = %s""",
            (team['team_id'],)
        )
        users = cursor.fetchall()
        for user in users:
            await bot.send_message(user['user_id'],
                                   f"Новое задание для вашей команды ({team['team_name']}): {task_text}")

    conn.commit()
    await state.clear()
    await message.answer("Задание отправлено всем пользователям!")

# Формирование команд (для администратора)
@dp.message(Command("form_teams"))
async def form_teams(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для этой команды!")
        return

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    # Получаем все направления
    directions = list(set(user['direction'] for user in users))

    # Очищаем существующие команды
    cursor.execute("DELETE FROM user_teams")
    cursor.execute("DELETE FROM teams")
    conn.commit()

    # Перемешиваем пользователей
    random.shuffle(users)

    # Создаем команды
    team_size = len(directions)
    teams = [[] for _ in range((len(users) + team_size - 1) // team_size)]

    # Распределяем пользователей по командам
    for i, user in enumerate(users):
        teams[i % len(teams)].append(user)

    # Проверяем наличие всех направлений в каждой команде
    for team in teams:
        team_directions = set(user['direction'] for user in team)
        if len(team_directions) < len(directions):
            for direction in directions:
                if direction not in team_directions:
                    for other_team in teams:
                        for user in other_team:
                            if user['direction'] == direction:
                                team.append(user)
                                other_team.remove(user)
                                break
                        if direction in set(u['direction'] for u in team):
                            break

    # Сохраняем команды в БД
    for i, team in enumerate(teams, 1):
        cursor.execute("INSERT INTO teams (team_name) VALUES (%s) RETURNING team_id",
                       (f"Команда {i}",))
        team_id = cursor.fetchone()['team_id']
        for user in team:
            cursor.execute("INSERT INTO user_teams (user_id, team_id) VALUES (%s, %s)",
                           (user['user_id'], team_id))

    conn.commit()
    await message.answer("Команды сформированы!")

# Показать информацию о команде
@dp.message(lambda message: message.text == "Моя команда")
async def my_team(message: Message):
    cursor.execute("""
        SELECT t.team_name, u.first_name, u.last_name, u.direction
        FROM users u
        JOIN user_teams ut ON u.user_id = ut.user_id
        JOIN teams t ON ut.team_id = t.team_id
        WHERE u.user_id = %s
    """, (message.from_user.id,))
    result = cursor.fetchone()

    if not result:
        await message.answer("Вы не состоите в команде!")
        return

    cursor.execute("""
        SELECT u.first_name, u.last_name, u.direction
        FROM users u
        JOIN user_teams ut ON u.user_id = ut.user_id
        WHERE ut.team_id = (SELECT team_id FROM user_teams WHERE user_id = %s)
    """, (message.from_user.id,))
    members = cursor.fetchall()

    response = f"Ваша команда: {result['team_name']}\n\nУчастники:\n"
    for member in members:
        response += f"{member['first_name']} {member['last_name']} ({member['direction']})\n"

    await message.answer(response)

# Статистика
@dp.message(lambda message: message.text == "Статистика")
async def statistics(message: Message):
    cursor.execute("""
        SELECT t.team_name, COUNT(tk.task_id) as completed_tasks
        FROM teams t
        LEFT JOIN tasks tk ON t.team_id = tk.team_id AND tk.is_completed = TRUE
        JOIN user_teams ut ON t.team_id = ut.team_id
        WHERE ut.user_id = %s
        GROUP BY t.team_name
    """, (message.from_user.id,))
    result = cursor.fetchone()

    if not result:
        await message.answer("Вы не состоите в команде!")
        return

    await message.answer(f"Команда: {result['team_name']}\nВыполнено заданий: {result['completed_tasks']}")

# Запуск бота
async def main():
    logging.info(f"Bot instance: {bot}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())