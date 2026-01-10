# How to Create a Telegram Bot from Scratch

This guide will walk you through the complete process of creating a Telegram bot from scratch, including bot creation, configuration, and integration with your application.

### Step 1: Start Chatting with BotFather

1. Open Telegram and search for `@BotFather`
2. Start a chat with BotFather
3. Send `/start` to begin

### Step 2: Create a New Bot

1. Send the `/newbot` command
2. Choose a name for your bot (display name)
3. Choose a username for your bot (must end with 'bot', e.g., `my_trading_bot`)
4. BotFather will provide you with a **bot token** - save it securely!

### Step 3: Get Your Bot Token

After creating the bot, BotFather will provide a token in the following format:
```
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

**Important Security Notes:**
- Never share this token publicly
- Store it in environment variables
- Use `.env` file for local development
- Use secure key management in production environments

### Step 4: Get Your Chat ID

Send any message to your newly created bot on Telegram.

Then replace {bot_token} in the following URL with the token provided when creating the bot, and enter the URL in your web browser:
https://api.telegram.org/bot{bot_token}/getUpdates

For example, if your token is `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`, change the URL to:
`https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/getUpdates`

After opening the URL, you will see information similar to the following:
```
{"ok":true,"result":[{"update_id":880712345,
"message":{"message_id":1,"from":{"id":5586512345,"is_bot":false,"first_name":"yourQuantGuy","username":"yourquantguy","language_code":"en","is_premium":true},"chat":{"id":5586512345,"first_name":"yourQuantGuy","username":"yourquantguy","type":"private"},"date":1759103123,"text":"/start","entities":[{"offset":0,"length":6,"type":"bot_command"}]}}]}
```

Find the id in "chat":{"id": ... }, which is 5586512345 in the example above.

### Step 5: Update .env File

Add your Telegram bot token and chat ID to the .env file in your script:
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

For example:
```
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID=5586512345
LANGUAGE=EN
```
