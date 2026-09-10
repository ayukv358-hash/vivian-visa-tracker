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


def log(message):
    print(f"[VISA TRACKER] {message}", flush=True)


def telegram(message: str):
    log("Sending Telegram message...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    response.raise_for_status()
    log("Telegram message sent successfully.")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass

    return {
        "available": False,
        "signature": "",
    }


def save_state(data):
    STATE_FILE.write_text(
        json.dumps(data, indent=2) + "\n"
    )


def extract_availability(text: str):
    lower = text.lower()

    negative_phrases = [
        "no appointments available",
        "no hay citas disponibles",
        "no hay disponibilidad",
        "sin disponibilidad",
        "no availability",
    ]

    if any(phrase in lower for phrase in negative_phrases):
        log("Explicit NO-AVAILABILITY message detected.")
        return None

    positive_patterns = [
        r"\bavailable\b",
        r"\bdisponible\b",
        r"\bavailability\b",
        r"\bdisponibilidad\b",
        r"\bcita\b",
        r"\bappointment\b",
    ]

    positive = any(
        re.search(pattern, lower)
        for pattern in positive_patterns
    )

    date_patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
        r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
    ]

    dates = []

    for pattern in date_patterns:
        dates.extend(
            re.findall(pattern, text, flags=re.IGNORECASE)
        )

    times = re.findall(
        r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b",
        text,
    )

    log(
        f"Detection scan: positive_words={positive}, "
        f"dates_found={len(dates)}, "
        f"times_found={len(times)}"
    )

    if positive and (dates or times):
        excerpt = re.sub(r"\s+", " ", text).strip()

        for marker in [
            "appointment",
            "cita",
            "available",
            "disponible",
            "availability",
            "disponibilidad",
        ]:
            index = excerpt.lower().find(marker)

            if index >= 0:
                excerpt = excerpt[
                    max(0, index - 150):
                    index + 700
                ]
                break

        return excerpt[:1000]

    return None


def main():
    log("========================================")
    log("SPAIN VISA APPOINTMENT CHECK STARTED")
    log("========================================")

    log("Opening CitaConsular...")

    state = load_state()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1280,
                "height": 900,
            }
        )

        try:
            page.goto(
                CITA_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            log("CitaConsular page loaded.")

            page.wait_for_timeout(5000)

            log(f"Page title: {page.title()}")
            log(f"Final URL: {page.url}")

            body = page.locator("body").inner_text(
                timeout=15000
            )

            log(
                f"Page text length: {len(body)} characters"
            )

            lower = body.lower()

            security_words = [
                "captcha",
                "verify you are human",
                "cloudflare",
                "security check",
            ]

            if any(
                word in lower
                for word in security_words
            ):
                log(
                    "SECURITY/CAPTCHA CHALLENGE DETECTED."
                )

                telegram(
                    "⚠️ 🇪🇸 Spain Visa Tracker\n\n"
                    "A security/CAPTCHA challenge appeared "
                    "on CitaConsular.\n\n"
                    "The tracker stopped safely. "
                    "Please open the booking page manually."
                )

                browser.close()
                return

            # Diagnostic information about the page.
            buttons = page.locator("button").count()
            links = page.locator("a").count()
            inputs = page.locator("input").count()

            log(
                f"Page elements: "
                f"buttons={buttons}, "
                f"links={links}, "
                f"inputs={inputs}"
            )

            # Show only useful diagnostic lines.
            useful_lines = []

            for line in body.splitlines():
                clean = re.sub(
                    r"\s+",
                    " ",
                    line
                ).strip()

                if not clean:
                    continue

                line_lower = clean.lower()

                keywords = [
                    "appointment",
                    "cita",
                    "available",
                    "disponible",
                    "availability",
                    "disponibilidad",
                    "calendar",
                    "calendario",
                    "september",
                    "october",
                    "november",
                    "december",
                ]

                if any(
                    keyword in line_lower
                    for keyword in keywords
                ):
                    useful_lines.append(clean[:200])

            log(
                f"Useful appointment-related lines found: "
                f"{len(useful_lines)}"
            )

            for line in useful_lines[:20]:
                log(f"PAGE: {line}")

            result = extract_availability(body)

            if result:
                log(
                    "🟢 POSSIBLE APPOINTMENT AVAILABILITY DETECTED."
                )
            else:
                log(
                    "⚪ NO APPOINTMENT AVAILABILITY DETECTED."
                )

        except Exception as error:
            log(
                f"ERROR while checking page: "
                f"{type(error).__name__}: {error}"
            )

            browser.close()
            raise

        browser.close()

    if result:
        signature = hashlib.sha256(
            result.encode("utf-8")
        ).hexdigest()

        if (
            not state.get("available")
            or state.get("signature") != signature
        ):
            message = (
                "🇪🇸 SPAIN — CAMEROON\n"
                "🟢 Student Visa\n\n"
                "📅 POSSIBLE APPOINTMENT "
                "AVAILABILITY DETECTED\n\n"
                f"Details from CitaConsular:\n"
                f"{result}\n\n"
                "👉 BOOK APPOINTMENT NOW:\n"
                f"{CITA_URL}"
            )

            telegram(message)

        else:
            log(
                "Availability already reported previously. "
                "No duplicate Telegram alert."
            )

        save_state(
            {
                "available": True,
                "signature": signature,
            }
        )

    else:
        save_state(
            {
                "available": False,
                "signature": "",
            }
        )

    log("========================================")
    log("CHECK COMPLETED")
    log("========================================")


if __name__ == "__main__":
    main()
