from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncpg
import asyncio
import pickle
import os
import re
import logging
from config import TOKEN, DB_CONFIG, CHECK_INTERVAL


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


bot = Bot(token=TOKEN)
dp = Dispatcher()



async def init_db():
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tracking (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                url TEXT NOT NULL,
                price TEXT,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("DELETE FROM tracking WHERE url NOT LIKE 'https://%'")
        await conn.close()
        logger.info("База готова!")
    except Exception as e:
        logger.error(f"Ошибка базы: {e}")



async def get_price(url):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = Service(executable_path="D:/Projects/Discount_bot_in_marketplaces/chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)

    try:
        if os.path.exists("cookies.pkl"):
            driver.get("https://www.ozon.ru")
            with open("cookies.pkl", "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    driver.add_cookie(cookie)
            logger.info("Cookies загружены из cookies.pkl")

        driver.get(url)
        logger.info("Загружаю страницу...")

        wait = WebDriverWait(driver, 30)
        price_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".l2y_29.yl0_29")))
        price = price_element.text
        logger.info(f"Нашёл цену с селектором .l2y_29.yl0_29: {price}")

        cookies = driver.get_cookies()
        with open("cookies.pkl", "wb") as f:
            pickle.dump(cookies, f)
        logger.info("Cookies сохранены в cookies.pkl")

        return price

    except Exception as e:
        logger.error(f"Ошибка Selenium: {e}")
        html_content = driver.page_source
        logger.error(f"HTML страницы (первые 1000 символов): {html_content[:1000]}")
        return "Цена не найдена"

    finally:
        driver.quit()



def parse_price(price_text):
    try:
        return int(re.sub(r'[^\d]', '', price_text))
    except:
        return None



async def handle_link(message: Message, url: str, user_id: int):
    try:
        current_price = await get_price(url)
        if current_price == "Цена не найдена":
            await message.reply("Не удалось найти цену.")
            return

        conn = await asyncpg.connect(**DB_CONFIG)

        prev_price_record = await conn.fetchrow(
            "SELECT price FROM tracking WHERE user_id = $1 AND url = $2 ORDER BY created_at DESC LIMIT 1",
            user_id, url
        )

        await conn.execute(
            "INSERT INTO tracking (user_id, url, price) VALUES ($1, $2, $3)",
            user_id, url, current_price
        )

        if prev_price_record:
            prev_price = prev_price_record['price']
            prev_price_num = parse_price(prev_price)
            current_price_num = parse_price(current_price)
            logger.info(f"Сравниваю: было {prev_price_num}, стало {current_price_num}")

            if prev_price_num and current_price_num:
                if current_price_num < prev_price_num:
                    await message.reply(
                        f"Цена упала! Было: {prev_price}, стало: {current_price}. Добавил в отслеживание!")
                elif current_price_num > prev_price_num:
                    await message.reply(
                        f"Цена выросла! Было: {prev_price}, стало: {current_price}. Добавил в отслеживание!")
                else:
                    await message.reply(f"Цена: {current_price}. Цена не изменилась. Добавил в отслеживание!")
            else:
                await message.reply(f"Цена: {current_price}. Добавил в отслеживание!")
        else:
            await message.reply(f"Цена: {current_price}. Добавил в отслеживание!")

        await conn.close()

    except Exception as e:
        await message.reply(f"Ошибка: {e}")



async def check_prices():
    logger.info("Запускаю фоновую проверку цен...")
    while True:
        try:
            conn = await asyncpg.connect(**DB_CONFIG)
            tracked_items = await conn.fetch("SELECT DISTINCT user_id, url FROM tracking")
            await conn.close()

            if not tracked_items:
                logger.info("Нет товаров для проверки.")
            else:
                for item in tracked_items:
                    user_id, url = item['user_id'], item['url']
                    logger.info(f"Проверяю цену для {url} (user_id: {user_id})")
                    current_price = await get_price(url)
                    if current_price == "Цена не найдена":
                        logger.warning(f"Не удалось найти цену для {url}")
                        continue

                    conn = await asyncpg.connect(**DB_CONFIG)
                    prev_price_record = await conn.fetchrow(
                        "SELECT price FROM tracking WHERE user_id = $1 AND url = $2 ORDER BY created_at DESC LIMIT 1",
                        user_id, url
                    )

                    await conn.execute(
                        "INSERT INTO tracking (user_id, url, price) VALUES ($1, $2, $3)",
                        user_id, url, current_price
                    )

                    if prev_price_record:
                        prev_price = prev_price_record['price']
                        prev_price_num = parse_price(prev_price)
                        current_price_num = parse_price(current_price)
                        logger.info(
                            f"Сравниваю в фоне для user_id {user_id}: было {prev_price_num}, стало {current_price_num}")

                        if prev_price_num and current_price_num:
                            if current_price_num < prev_price_num:
                                await bot.send_message(user_id,
                                                       f"Цена упала для {url}! Было: {prev_price}, стало: {current_price}.")
                                logger.info(f"Уведомление отправлено user_id {user_id}: цена упала для {url}")
                            elif current_price_num > prev_price_num:
                                await bot.send_message(user_id,
                                                       f"Цена выросла для {url}! Было: {prev_price}, стало: {current_price}.")
                                logger.info(f"Уведомление отправлено user_id {user_id}: цена выросла для {url}")
                            else:
                                await bot.send_message(user_id, f"Цена для {url} не изменилась: {current_price}.")
                                logger.info(f"Уведомление отправлено user_id {user_id}: цена не изменилась для {url}")

                    await conn.close()

        except Exception as e:
            logger.error(f"Ошибка при проверке цен: {e}")

        logger.info(f"Жду {CHECK_INTERVAL} секунд перед следующей проверкой...")
        await asyncio.sleep(CHECK_INTERVAL)



@dp.message(Command("start"))
async def start(message: Message):
    await message.reply("Привет! Я бот скидок. Кидай ссылку на товар с Ozon, и я буду отслеживать цену!")


@dp.message()
async def handle_message(message: Message):
    url = message.text
    user_id = message.from_user.id
    if "ozon.ru" in url:
        await handle_link(message, url, user_id)
    else:
        await message.reply("Пока работаю только с Ozon.")



async def main():
    await init_db()
    asyncio.create_task(check_prices())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())