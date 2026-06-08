import json
import os
import smtplib
from email.mime.text import MIMEText
import time
from concurrent.futures import ThreadPoolExecutor
import requests



CONFIG_FILE = "config.json"
SLOW_THRESHOLD_MS = 500
TIMEOUT_SECONDS = 5.0
MAX_RETRIES = 2

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your_email@gmail.com"
SENDER_PASSWORD = "your_app_password"
RECEIVER_EMAIL = "admin@example.com"


def load_servers() -> list:

    env_servers = os.getenv("SERVERS")
    if env_servers:
        urls = [url.strip().strip("<>") for url in env_servers.split(",")]
        print(f"Loaded {len(urls)} servers from environment variable.")
        return urls

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                urls = [url.strip("<>") for url in config.get("servers", [])]
                print(f"Loaded {len(urls)} servers from config file.")
                return urls
        except json.JSONDecodeError:
            print(f"Error: {CONFIG_FILE} is not a valid JSON file.")

    raise FileNotFoundError(
        "Configuration error: Set 'SERVERS' env variable or create a valid 'config.json'."
    )


def send_email_alert(failed_urls: list):
    if not failed_urls:
        return

    subject = "⚠️ ALERT: Server Outage Detected!"
    body = f"The following services failed their health checks:\n\n" + "\n".join(
        failed_urls
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print("\n[ALERT] Notification email sent to administrator.")
    except Exception as e:
        print(f"\n[ALERT] Failed to send email notification: {e}")


def check_server(url: str) -> dict:
    result = {
        "url": url,
        "status": "DOWN",
        "status_code": None,
        "response_time_ms": None,
        "is_slow": False,
    }


    for attempt in range(1 + MAX_RETRIES):
        try:
            start_time = time.perf_counter()

            response = requests.get(url, timeout=TIMEOUT_SECONDS)

            elapsed_time_ms = int((time.perf_counter() - start_time) * 1000)
            result["response_time_ms"] = elapsed_time_ms
            result["status_code"] = response.status_code

            if elapsed_time_ms > SLOW_THRESHOLD_MS:
                result["is_slow"] = True

            if 200 <= response.status_code < 300:
                result["status"] = "OK"

                try:
                    json_data = response.json()
                    if "status" in json_data and json_data["status"] != "ok":
                        result["status"] = "DOWN"
                except ValueError:
                    pass

            if response.status_code < 500:
                break

        except (requests.exceptions.RequestException, requests.exceptions.Timeout):
            result["status"] = "TIMEOUT" if attempt == MAX_RETRIES else "DOWN"

    return result


def format_result(result: dict) -> str:
    url = result["url"]
    status = result["status"]
    code = result["status_code"]
    time_ms = result["response_time_ms"]
    is_slow = result["is_slow"]

    clean_url = url.replace("https://", "").replace("http://", "")

    if status == "OK":
        slow_tag = "  [slow]" if is_slow else ""
        return f"{clean_url:<30} — OK ({code})    — {time_ms}ms{slow_tag}"
    elif status == "TIMEOUT":
        return f"{clean_url:<30} — TIMEOUT"
    else:
        code_str = f" ({code})" if code else ""
        return f"{clean_url:<30} — DOWN{code_str}"


def check_all_servers():
    try:
        urls = load_servers()
    except Exception as e:
        print(e)
        return

    print("\nStarting Server Health Checks...\n" + "—" * 50)


    failed_services = []
    results = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(check_server, urls))

    for res in results:
        print(format_result(res))
        if res["status"] in ["DOWN", "TIMEOUT"]:
            failed_services.append(res["url"])

    print("—" * 50)

    if failed_services:
        clean_failed = [
            u.replace("https://", "").replace("http://", "") for u in failed_services
        ]
        print(f"\nFailed services: {', '.join(clean_failed)}")

    else:

        print("\nAll services are healthy! 🎉")


if __name__ == "__main__":
    check_all_servers()