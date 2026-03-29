# Telegram Personal Assistant Bot

A personal-use Telegram bot for downloading media from:

- YouTube
- YouTube Music
- Public Instagram posts, reels, photos, and carousels

## Features

- YouTube audio and video downloads
- YouTube Music audio-only flow
- Instagram auto-detection for image, video, and carousel posts
- Inline cancel buttons before and during processing
- Live progress status message in Telegram
- Admin process monitor with stop controls
- Activity tracking in `logs/activity.jsonl`
- Error-only bot logs in `logs/bot.log`
- Docker support with FFmpeg included

## Project Structure

```text
bot/
  main.py
  config.py
  services/
  utils/
downloads/
logs/
requirements.txt
Dockerfile
```

## Requirements

- Python 3.12+
- FFmpeg
- Telegram bot token

## Environment

Create `.env` with:

```env
BOT_TOKEN=your_bot_token_here
ADMIN_CHAT_IDS=123456789
INSTAGRAM_COOKIES_FILE=
INSTAGRAM_COOKIES_FROM_BROWSER=
```

You can set multiple admins with commas:

```env
ADMIN_CHAT_IDS=123456789,987654321
```

For Instagram posts that redirect to the login page, configure one of these:

```env
INSTAGRAM_COOKIES_FILE=/absolute/path/to/cookies.txt
```

or:

```env
INSTAGRAM_COOKIES_FROM_BROWSER=firefox/instagram
```

## Local Run

Install dependencies:

```bash
python -m venv myenv
myenv/bin/pip install -r requirements.txt
```

Start the bot:

```bash
myenv/bin/python -m bot.main
```

## Docker

Build:

```bash
docker build -t telegram-pa-bot .
```

Run:

```bash
docker run --env-file .env telegram-pa-bot
```

## Bot Commands

- `/start` show welcome text
- `/help` show help
- `/processes` admin view of active downloads
- `/todaylogs` admin summary of today's activity
- `/todaylogs username` admin filtered summary for one user

## Logging

- `logs/bot.log`
  Error log only
- `logs/activity.jsonl`
  Structured activity events such as requests, failures, cancellations, and completion durations

## Notes

- Temporary downloaded files are removed after processing.
- Instagram support is for public links only.
- Some Instagram posts require a logged-in session. Use `INSTAGRAM_COOKIES_FILE` or `INSTAGRAM_COOKIES_FROM_BROWSER` when Instagram redirects to login.
- Cancellation is best-effort once Telegram has already accepted an upload request.
- If the bot token has been exposed, rotate it before production use.
