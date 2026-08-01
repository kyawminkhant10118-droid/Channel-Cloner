# Channel Cloner Bot

Telegram Channel Cloner Bot - forward/clone messages from source channels to destination channels automatically.

## Features

- Auto clone messages (text, photo, video, document, audio, voice, sticker, animation)
- Album/Media Group support
- Protected/Restricted content download & re-upload
- Inline button control panel
- Text filters (remove links, @mentions, #hashtags)
- Custom header & footer text
- Configurable clone delay
- Pause/Resume
- Per-route enable/disable toggle
- Duplicate prevention
- FloodWait auto-retry
- SQLite database persistence
- Deploy on Railway

## Requirements

1. **Telegram API Credentials** - Get from https://my.telegram.org
   - `API_ID`
   - `API_HASH`
2. **Session String** - Generate using [Pyrofork Session Generator](https://replit.com/@pyrofork/Session-Generator)
3. **Bot Token** - Create a bot via [@BotFather](https://t.me/BotFather)
4. **Owner ID** - Your Telegram user ID (get from [@userinfobot](https://t.me/userinfobot))

## Deploy on Railway

### Method 1: Docker (Recommended)

1. Go to [railway.app](https://railway.app) and create a new project
2. Click **"Deploy from GitHub repo"** and select this repository
3. Railway will auto-detect the Dockerfile
4. Add these environment variables in Railway:

| Variable | Description | Required |
|----------|-------------|----------|
| `API_ID` | Telegram API ID | Yes |
| `API_HASH` | Telegram API Hash | Yes |
| `SESSION_STRING` | Pyrofork session string | Yes |
| `BOT_TOKEN` | Telegram Bot token | Yes |
| `OWNER_ID` | Your Telegram user ID | Yes |
| `LOG_CHANNEL` | Channel ID for logs (optional) | No |

5. Deploy!

### Method 2: Nixpacks (No Dockerfile)

Railway also supports Nixpacks. Just connect the repo and set the env vars. The `nixpacks.toml` and `Procfile` are already configured.

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` or `/menu` | Open control panel |
| `/route <src> <dst>` | Add clone route |
| `/unroute <src_id> <dst_id>` | Remove route |
| `/routes` | List all routes |
| `/toggle <src_id> <dst_id>` | Enable/disable route |
| `/set_header <text>` | Set header text |
| `/set_footer <text>` | Set footer text |
| `/setdelay <seconds>` | Set clone delay |
| `/status` | View bot status |

## Usage Example

```
/route @sourcechannel @mychannel
/route -1001234567890 -1009876543210
/routes
/set_header Promoted Content
/set_footer Follow @mychannel
/setdelay 2
/status
```

## Notes

- The userbot account must be a **member** of both source and destination channels
- For protected channels, the bot will download and re-upload content automatically
- Album groups are handled with a 2.5s buffer to collect all media
- Never share your `SESSION_STRING` - it gives full access to your Telegram account

## Tech Stack

- [Pyrofork](https://github.com/Mayuri-Chan/pyrofork) - Telegram Client (Pyrogram fork)
- [tgcrypto](https://github.com/pyrogram/tgcrypto) - Fast crypto for Telegram
- [aiosqlite](https://github.com/aiosqlite/aiosqlite) - Async SQLite
- [Railway](https://railway.app) - Hosting platform

## License

MIT