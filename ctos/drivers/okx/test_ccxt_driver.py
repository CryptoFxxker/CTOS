
import os
import ccxt

def mask(s: str, left=3, right=3):
    if not s:
        return None
    s = str(s)
    if len(s) <= left + right:
        return "*" * len(s)
    return s[:left] + "*" * (len(s) - left - right) + s[-right:]

def main():
    api_key = "059a3889-331c-4bde-a9c5-4685f9fe117b"
    secret  = "05A34DA4ADC896711BE3A4E12ED4E2CD"
    pwd     = "Jj.20251209"

    print("ENV OKX_API_KEY      :", mask(api_key))
    print("ENV OKX_SECRET_KEY   :", mask(secret))
    print("ENV OKX_PASSPHRASE   :", mask(pwd))

    # 关键：strip 一下，避免末尾换行/空格导致 ccxt 认为是空
    api_key = (api_key or "").strip()
    secret  = (secret or "").strip()
    pwd     = (pwd or "").strip()

    exchange = ccxt.okx({
        "apiKey": api_key,
        "secret": secret,
        "password": pwd,
        "enableRateLimit": True,
        "proxies": {
            "https": "socks5h://127.0.0.1:1080",
            "http": "socks5h://127.0.0.1:1080"
        },
        "options": {
            "adjustForTimeDifference": True,
        }
    })

    # 关键：直接验证“当前实例”里 ccxt 看到的凭证是什么
    print("EXCHANGE apiKey      :", mask(getattr(exchange, "apiKey", None)))
    print("EXCHANGE secret      :", "SET" if getattr(exchange, "secret", None) else None)
    print("EXCHANGE password    :", "SET" if getattr(exchange, "password", None) else None)

    # 如果这里显示 EXCHANGE apiKey 是 None，那就说明你用错实例或被覆盖
    exchange.load_markets()

    balance = exchange.fetch_balance()
    print("USDT:", balance.get("USDT"))

if __name__ == "__main__":
    main()
