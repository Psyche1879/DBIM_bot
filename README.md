# Discount Bot in Marketplaces (DBIM_bot)

Telegram-бот для отслеживания цен на товары с маркетплейса Ozon. Бот уведомляет пользователей об изменениях цен, помогая находить скидки.

## Возможности
- Отслеживание цен на товары с Ozon по ссылке.
- Уведомления о снижении или повышении цены.
- Фоновая проверка цен с заданным интервалом.
- Хранение истории цен в базе данных PostgreSQL.

## Требования
- Python 3.8+
- PostgreSQL
- ChromeDriver (для Selenium)
- Telegram-токен от BotFather

## Установка
1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/Psyche1879/DBIM_bot.git
   cd DBIM_bot