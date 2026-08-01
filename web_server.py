from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import aiosqlite
import time
import os
import asyncio

DB_FILE = "cloner.db"
PORT = int(os.environ.get("PORT", 8080))

app = FastAPI(title="Channel Cloner Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import globals from bot
START_TIME = time.time()


def get_bot_globals():
    """Get live bot stats from bot module."""
    try:
        import bot
        return {
            "cloned": bot.CLONED_COUNT,
            "failed": bot.FAILED_COUNT,
            "start_time": bot.START_TIME,
            "cache_size": len(bot.PROCESSED_MSGS),
        }
    except Exception:
        return {"cloned": 0, "failed": 0, "start_time": START_TIME, "cache_size": 0}


async def db_get(key, default=""):
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT value FROM config WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception:
        return default


async def db_set(key, value):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()


# =========================================
# PAGES
# =========================================
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>dashboard.html not found</h1>")


# =========================================
# API - STATUS
# =========================================
@app.get("/api/status")
async def api_status():
    g = get_bot_globals()
    uptime = time.time() - g["start_time"]
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    
    is_paused = (await db_get("is_paused")) == "true"
    
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM routes WHERE is_active = 1") as cur:
            active_routes = (await cur.fetchone())[0]

    return {
        "is_paused": is_paused,
        "cloned": g["cloned"],
        "failed": g["failed"],
        "uptime_hours": hours,
        "uptime_mins": mins,
        "active_routes": active_routes,
        "cache_size": g["cache_size"],
    }


# =========================================
# API - CONFIG
# =========================================
@app.get("/api/config")
async def api_get_config():
    return {
        "is_paused": (await db_get("is_paused")) == "true",
        "remove_links": (await db_get("remove_links")) == "true",
        "remove_usernames": (await db_get("remove_usernames")) == "true",
        "remove_hashtags": (await db_get("remove_hashtags")) == "true",
        "skip_forwarded": (await db_get("skip_forwarded")) == "true",
        "header_text": await db_get("header_text"),
        "footer_text": await db_get("footer_text"),
        "clone_delay": await db_get("clone_delay", "1"),
    }


@app.post("/api/config")
async def api_set_config(request: Request):
    data = await request.json()
    for key, value in data.items():
        if key in ["is_paused", "remove_links", "remove_usernames", "remove_hashtags", "skip_forwarded"]:
            await db_set(key, "true" if value else "false")
        elif key in ["header_text", "footer_text", "clone_delay"]:
            await db_set(key, str(value))
    return {"ok": True}


# =========================================
# API - ROUTES
# =========================================
@app.get("/api/routes")
async def api_get_routes():
    routes = []
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT source_id, source_name, dest_id, dest_name, is_active, created_at FROM routes ORDER BY id DESC") as cur:
                async for row in cur:
                    routes.append({
                        "source_id": row[0],
                        "source_name": row[1] or "",
                        "dest_id": row[2],
                        "dest_name": row[3] or "",
                        "is_active": bool(row[4]),
                        "created_at": row[5] or "",
                    })
    except Exception:
        pass
    return {"routes": routes}


@app.post("/api/routes")
async def api_add_route(request: Request):
    data = await request.json()
    source = data.get("source", "")
    dest = data.get("dest", "")
    
    if not source or not dest:
        raise HTTPException(400, "Source and dest required")

    # Resolve IDs
    try:
        import bot
        src_chat = await bot.userbot.get_chat(source)
        dst_chat = await bot.userbot.get_chat(dest)
        src_id, src_name = src_chat.id, src_chat.title or ""
        dst_id, dst_name = dst_chat.id, dst_chat.title or ""
    except Exception as e:
        raise HTTPException(400, f"Channel error: {e}")

    async with aiosqlite.connect(DB_FILE) as db:
        try:
            await db.execute(
                "INSERT INTO routes (source_id, dest_id, source_name, dest_name) VALUES (?, ?, ?, ?)",
                (src_id, dst_id, src_name, dst_name)
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, "Route already exists")

    return {"ok": True, "source_id": src_id, "dest_id": dst_id}


@app.delete("/api/routes")
async def api_delete_route(request: Request):
    data = await request.json()
    src_id = data.get("source_id")
    dst_id = data.get("dest_id")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM routes WHERE source_id = ? AND dest_id = ?", (src_id, dst_id))
        await db.commit()
    return {"ok": True}


@app.post("/api/routes/toggle")
async def api_toggle_route(request: Request):
    data = await request.json()
    src_id = data.get("source_id")
    dst_id = data.get("dest_id")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE routes SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE source_id = ? AND dest_id = ?",
            (src_id, dst_id)
        )
        await db.commit()
    return {"ok": True}


# =========================================
# RUN SERVER (called from bot.py)
# =========================================
async def start_web_server():
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
