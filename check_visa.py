import os
import json
import re
import hashlib
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

CITA_URL = os.environ["CITA_URL"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path("state.json")

def telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }, timeout=20)
    r.raise_for_status()

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"available": False, "signature": ""}

def save_state(data):
    STATE_FILE.write_text(json.dumps(data, indent=2) + "\n")

def extract_availability(text: str):
    # We intentionally use broad detection first. Once we inspect the real
    # CitaConsular page, these patterns/selectors can be tightened.
    lower = text.lower()

    negative_phrases = [
        "no appointments available",
        "no hay citas disponibles",
        "no hay disponibilidad",
        "sin disponibilidad",
        "no availability",
    ]
    if any(p in lower for p in negative_phrases):
        return None

    positive_patterns = [
        r"\b(?:available|disponible|availability)\b",
        r"\b\d{1,2}[:.]\d{2}\b",
    ]
    positive = any(re.search(p, lower) for p in positive_patterns)

    # Look for date/time-like information near the appointment section.
    date_patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
        r"\b\d{1,2}\s+(?:september|october|november|december)\b",
    ]
    dates = []
    for p in date_patterns:
        dates.extend(re.findall(p, text, flags=re.I))

    times = re.findall(r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b", text)

    if positive and (dates or times):
        # Keep only a bounded excerpt so Telegram messages stay readable.
        excerpt = re.sub(r"\s+", " ", text).strip()
        for marker in ["appointment", "cita", "available", "disponible"]:
            idx = excerpt.lower().find(marker)
            if idx >= 0:
                excerpt = excerpt[max(0, idx-150):idx+700]
                break
        return excerpt[:1000]

    return None

def main():
    state = load_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(CITA_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # Do not attempt to defeat CAPTCHAs or security challenges.
        body = page.locator("body").inner_text(timeout=15000)
        lower = body.lower()
        security_words = ["captcha", "verify you are human", "cloudflare", "security check"]
        if any(x in lower for x in security_words):
            telegram("⚠️ 🇪🇸 Spain Visa Tracker\nA security/CAPTCHA challenge appeared on CitaConsular. I stopped the check — please open the booking page manually.")
            browser.close()
            return

        result = extract_availability(body)
        browser.close()

    if result:
        signature = hashlib.sha256(result.encode("utf-8")).hexdigest()
        if not state.get("available") or state.get("signature") != signature:
            message = (
                "🇪🇸 SPAIN — CAMEROON\n"
                "🟢 Student Visa\n"
                "📅 POSSIBLE APPOINTMENT AVAILABILITY DETECTED\n\n"
                f"Details from CitaConsular:\n{result}\n\n"
                "👉 BOOK APPOINTMENT NOW:\n"
                f"{CITA_URL}"
            )
            telegram(message)
        save_state({"available": True, "signature": signature})
    else:
        # Clearing the state lets us alert again if availability disappears
        # and later returns.
        save_state({"available": False, "signature": ""})

if __name__ == "__main__":
    main()
