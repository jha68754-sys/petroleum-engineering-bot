import os
import requests
import time

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

offset = 0

SYSTEM_PROMPT = """
You are a professional AI assistant specialized in Petroleum Engineering and PVT Lab.
Answer in the same language as the user.
Support Arabic and English.
Explain PVT, CCE, CVD, DL, EOS, GOR, Bo, Rs, viscosity, Eclipse, CMG and reservoir engineering topics.
"""

def ask_ai(user_text):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.4
    }

    response = requests.post(
        GROQ_URL,
        headers=headers,
        json=payload,
        timeout=60
    )

    data = response.json()

    if "choices" in data:
        return data["choices"][0]["message"]["content"]

    return str(data)[:1000]

def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text[:4000]
        }
    )

while True:
    try:
        updates = requests.get(
            f"{TELEGRAM_URL}/getUpdates",
            params={
                "offset": offset + 1,
                "timeout": 30
            },
            timeout=40
        ).json()

        for update in updates.get("result", []):
            offset = update["update_id"]

            if "message" in update and "text" in update["message"]:
                chat_id = update["message"]["chat"]["id"]
                text = update["message"]["text"]

                if text == "/start":
                    reply = "👋 أهلاً بك في PVT Lab AI Bot"
                else:
                    reply = ask_ai(text)

                send_message(chat_id, reply)

    except Exception as e:
        print(e)

    time.sleep(1)
