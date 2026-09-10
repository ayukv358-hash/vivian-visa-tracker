# Vivian Visa Tracker

Automated checker for the Spain/Yaoundé CitaConsular appointment page.

## What it does
- Runs on GitHub Actions.
- Opens the CitaConsular page with Chromium/Playwright.
- Detects possible appointment availability.
- Sends an alert to Telegram.
- Stores the last detected state to reduce duplicate alerts.

## Safety
The checker does not bypass CAPTCHA, Cloudflare, rate limits, or other security controls. If a security challenge appears, it stops and alerts the user.

## Secrets
Configure these GitHub Actions secrets:
- `CITA_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
