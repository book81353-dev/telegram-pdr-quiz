import asyncio
import os
import random
from typing import Dict, Any, List

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("ПОМИЛКА: Змінна BOT_TOKEN не знайдена!")

QUESTIONS = [
    {
        "id": 1,
        "question": "🚗 Хто має перевагу на рівнозначному перехресті, якщо справа наближається автомобіль?",
        "answers": ["Я маю перевагу", "Потрібно поступитися автомобілю справа"],
        "correct": 1,
        "explanation": "<b>ПДР 16.12:</b> На перехресті рівнозначних доріг водій зобов'язаний дати дорогу ТЗ, що наближаються праворуч.",
        "image": None
    },
    {
        "id": 2,
        "question": "🚦 Що означає червоний сигнал світлофора?",
        "answers": ["Рух заборонено", "Можна продовжувати рух"],
        "correct": 0,
        "explanation": "<b>ПДР 8.7.3 (е):</b> Червоний сигнал забороняє рух.",
        "image": None
    },
    {
        "id": 3,
        "question": "🏙️ Яка загальна дозволена швидкість у населених пунктах України?",
        "answers": ["50 км/год", "70 км/год", "90 км/год"],
        "correct": 0,
        "explanation": "<b>ПДР 12.4:</b> У населених пунктах рух дозволяється зі швидкістю не більше 50 км/год.",
        "image": None
    },
    {
        "id": 4,
        "question": "🛑 Що означає знак 2.2 «Проїзд без зупинки заборонено» (STOP)?",
        "answers": [
            "Зупинка заборонена",
            "Потрібно обов'язково зупинитися перед розміткою чи знаком",
            "Можна їхати без зупинки, якщо немає перешкод"
        ],
        "correct": 1,
        "explanation": "<b>Знак 2.2:</b> Забороняється рух без зупинки перед стоп-лінією або знаком.",
        "image": None
    },
    {
        "id": 5,
        "question": "🚘 Хто повинен користуватися ременем безпеки?",
        "answers": [
            "Тільки водій",
            "Тільки пасажир спереду",
            "Водій і всі пасажири, якщо вони передбачені конструкцією"
        ],
        "correct": 2,
        "explanation": "<b>ПДР 2.3 (в):</b> Водій та пасажири зобов'язані бути застебнутими ременями безпеки.",
        "image": None
    }
]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

users: Dict[int, Dict[str, Any]] = {}
user_wrong_answers: Dict[int, List[int]] = {}

def build_keyboard(buttons: dict, adjust: int = 1) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, callback_data in buttons.items():
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(adjust)
    return builder.as_markup()

async def render_question(event: types.Message | types.CallbackQuery, user_id: int, edit: bool = False):
    session = users[user_id]
    idx = session["current"]
    question_data = session["questions"][idx]
    total = len(session["questions"])

    mode_title = "🎓 Екзамен" if session["mode"] == "exam" else "📋 Тестування"
    text = (
        f"<b>{mode_title} — Питання {idx + 1} з {total}</b>\n"
        f"❌ Помилок: {session['errors_count']}/2\n\n" if session["mode"] == "exam" else "\n"
    ) + f"{question_data['question']}"

    btn_dict = {ans: f"answer:{i}" for i, ans in enumerate(question_data["answers"])}
    markup = build_keyboard(btn_dict)

    target_message = event.message if isinstance(event, types.CallbackQuery) else event
    image = question_data.get("image")

    if image:
        if edit:
            media = types.InputMediaPhoto(media=image, caption=text)
            await target_message.edit_media(media=media, reply_markup=markup)
        else:
            await target_message.answer_photo(photo=image, caption=text, reply_markup=markup)
    else:
        if edit and target_message.photo:
            await target_message.delete()
            await target_message.answer(text, reply_markup=markup)
        elif edit:
            await target_message.edit_text(text, reply_markup=markup)
        else:
            await target_message.answer(text, reply_markup=markup)

@dp.message(Command("start", "quiz"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    has_errors = bool(user_wrong_answers.get(user_id))

    buttons = {
        "🚦 Звичайний тест": "mode:practice",
        "🎓 Екзамен ГСЦ (макс 2 помилки)": "mode:exam"
    }
    if has_errors:
        buttons["🛠️ Робота над помилками"] = "mode:errors"

    await message.answer(
        "👋 <b>Ласкаво просимо до тренажера ПДР України!</b>\n\nОберіть режим навчання:",
        reply_markup=build_keyboard(buttons)
    )

@dp.callback_query(F.data.startswith("mode:"))
async def start_selected_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    mode = callback.data.split(":")[1]

    if mode == "errors":
        wrong_ids = user_wrong_answers.get(user_id, [])
        selected_questions = [q for q in QUESTIONS if q["id"] in wrong_ids]
    else:
        selected_questions = QUESTIONS.copy()
        random.shuffle(selected_questions)

    if not selected_questions:
        await callback.answer("У вас немає незбережених помилок!", show_alert=True)
        return

    users[user_id] = {
        "questions": selected_questions,
        "current": 0,
        "score": 0,
        "errors_count": 0,
        "mode": mode,
        "is_answering": False
    }

    await callback.answer()
    await render_question(callback, user_id, edit=True)

@dp.callback_query(F.data.startswith("answer:"))
async def handle_answer(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    session = users.get(user_id)

    if not session or session["is_answering"]:
        await callback.answer()
        return

    session["is_answering"] = True
    answer_idx = int(callback.data.split(":")[1])
    current_q = session["questions"][session["current"]]

    is_correct = (answer_idx == current_q["correct"])

    if is_correct:
        session["score"] += 1
        header = "✅ <b>Правильно!</b>"
        if current_q["id"] in user_wrong_answers.get(user_id, []):
            user_wrong_answers[user_id].remove(current_q["id"])
    else:
        session["errors_count"] += 1
        if user_id not in user_wrong_answers:
            user_wrong_answers[user_id] = []
        if current_q["id"] not in user_wrong_answers[user_id]:
            user_wrong_answers[user_id].append(current_q["id"])

        correct_text = current_q["answers"][current_q["correct"]]
        header = f"❌ <b>Неправильно!</b>\nПравильна відповідь: <i>{correct_text}</i>"

    text = f"{header}\n\n💡 {current_q['explanation']}"

    if session["mode"] == "exam" and session["errors_count"] > 2:
        text += "\n\n🛑 <b>Екзамен не складено!</b> Ви припустилися більше 2 помилок."
        buttons = {"🔄 Спробувати знов": "mode:exam", "🏠 Головне меню": "start_menu"}
        await callback.message.edit_text(text, reply_markup=build_keyboard(buttons))
        del users[user_id]
        await callback.answer()
        return

    is_last = (session["current"] + 1 >= len(session["questions"]))
    next_btn_text = "🏁 Переглянути результат" if is_last else "➡️ Наступне питання"
    next_btn_data = "finish_quiz" if is_last else "next_question"

    await callback.message.edit_text(text, reply_markup=build_keyboard({next_btn_text: next_btn_data}))
    await callback.answer()

@dp.callback_query(F.data == "next_question")
async def next_question(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    session = users.get(user_id)

    if not session:
        await callback.answer("Сесію завершено.", show_alert=True)
        return

    session["current"] += 1
    session["is_answering"] = False
    await render_question(callback, user_id, edit=True)
    await callback.answer()

@dp.callback_query(F.data == "finish_quiz")
async def finish_quiz(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    session = users.get(user_id)

    if not session:
        await callback.answer()
        return

    score = session["score"]
    total = len(session["questions"])
    pct = round((score / total) * 100)

    result_text = f"🏁 <b>Тест завершено!</b>\n\nРезультат: <b>{score} з {total}</b> ({pct}%)\n"

    buttons = {"🔄 Звичайний тест": "mode:practice", "🎓 Екзамен": "mode:exam"}
    if user_wrong_answers.get(user_id):
        buttons["🛠️ Робота над помилками"] = "mode:errors"

    await callback.message.edit_text(result_text, reply_markup=build_keyboard(buttons))
    del users[user_id]
    await callback.answer()

@dp.callback_query(F.data == "start_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)

async def main():
    print("🚀 Бот запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
