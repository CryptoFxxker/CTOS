# 如何从零开始创建 Telegram 机器人

本指南将带您完成从零开始创建 Telegram 机器人的完整过程，包括机器人创建、配置以及与您的应用程序集成。

### 步骤 1：与 BotFather 开始聊天

1. 打开 Telegram 并搜索 `@BotFather`
2. 与 BotFather 开始聊天
3. 发送 `/start` 开始

### 步骤 2：创建新机器人

1. 发送 `/newbot` 命令
2. 为您的机器人选择一个名称（显示名称）
3. 为您的机器人选择一个用户名（必须以 'bot' 结尾，例如 `my_trading_bot`）
4. BotFather 将为您提供一个**机器人令牌** - 请安全保存！

### 步骤 3：获取您的机器人令牌

创建机器人后，BotFather 将提供一个如下格式的令牌：
```
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

**重要安全注意事项：**
- 永远不要公开分享此令牌
- 将其存储在环境变量中
- 在本地开发中使用 `.env` 文件
- 在生产环境中使用安全的密钥管理

### 步骤 4：获取您的对话 ID

给你新创建的机器人在Telegram上发一条任意信息。

然后将以下网址中的{bot_token}用创建机器人时提供的令牌代替，在网页中输入以下网址：
https://api.telegram.org/bot{bot_token}/getUpdates

例如，如果你的令牌是 `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`,则将网址改为：
`https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/getUpdates`


打开网之后，你会看到类似于以下的信息：
```
{"ok":true,"result":[{"update_id":880712345,
"message":{"message_id":1,"from":{"id":5586512345,"is_bot":false,"first_name":"yourQuantGuy","username":"yourquantguy","language_code":"en","is_premium":true},"chat":{"id":5586512345,"first_name":"yourQuantGuy","username":"yourquantguy","type":"private"},"date":1759103123,"text":"/start","entities":[{"offset":0,"length":6,"type":"bot_command"}]}}]}
```

找到 "chat":{"id": ... }中的 id，即示例中的 5586512345。

### 步骤 5：更新 .env 文件
在脚本的 .env 文件中加入你的Telegram机器人令牌，以及对话ID。
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

比如：
```
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID=5586512345
LANGUAGE=CN
```
