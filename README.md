# Telegram Channel Cloner Bot

High-speed Telegram Channel Cloner Bot built with Telethon, optimized for streaming media and bypassing restricted content restrictions.

## Features
- Bypasses `Save Content Restricted` (Forward disabled) channels.
- Fixes video streaming bug (`supports_streaming=True`).
- Clean FFmpeg thumbnail extraction (Fixes white thumbnail issue).
- Real-time multi-source monitoring.

## Deployment Environment Variables
- `API_ID` : Telegram API ID
- `API_HASH` : Telegram API Hash
- `SESSION_STRING` : Telethon String Session
- `BOT_TOKEN` : Telegram Bot Token (Optional if using SESSION_STRING)
- `ADMIN_IDS` : Admin Telegram User IDs (Comma-separated)
