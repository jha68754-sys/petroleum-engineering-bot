import requests
import time

TOKEN = "8930247827:AAFlPeIl5-6GD-ZMt1Wfof9r_0Axqh3A-sY"

URL = f"https://api.telegram.org/bot{TOKEN}"

offset = 0

while True:
    try:
        r = requests.get(
            f"{URL}/getUpdates",
            params={"offset": offset + 1, "timeout": 30}
        ).json()

        for update in r.get("result", []):
            offset = update["update_id"]

            if "message" in update:
                chat_id = update["message"]["chat"]["id"]

                if "text" in update["message"]:
                    text = update["message"]["text"]

                    requests.post(
                        f"{URL}/sendMessage",
                        data={
                            "chat_id": chat_id,
                            "text": f"You said: {text}"
                        }
                    )

    except Exception as e:
        print(e)

    time.sleep(1)
