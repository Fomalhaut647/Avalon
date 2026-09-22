"""HTTP 接口。路由一览：

GET  /                              裁判席页面（单页应用，其余画面由前端按地址片段切换）
GET  /api/config                    新开一局表单的默认值、是否配了 API key、并发上限
GET  /api/games                     对局列表与跨局统计
POST /api/games                     新开若干局
GET  /api/games/{id}                一局摘要
GET  /api/games/{id}/events?since=N 事件列表（回放与首屏用）
GET  /api/games/{id}/stream         该局的事件流（SSE），支持 Last-Event-ID 续传
GET  /api/stream                    全部对局的摘要变化（SSE），对局列表页用
POST /api/games/{id}/pause          暂停：运行中按一下软暂停，等待中再按一下掐断进行中的调用
POST /api/games/{id}/resume         继续
POST /api/games/{id}/terminate      终止
GET  /api/games/{id}/players/{pid}  一名玩家的完整消息线程
GET  /api/games/{id}/files/{name}   下载或在线读取产物文件

事件流用 SSE 而不是 WebSocket：浏览器到服务只有几个控制请求，不需要反向长连接；SSE 自带断线续传。
"""

from __future__ import annotations

import json
import queue
from collections.abc import AsyncIterator

import anyio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from avalon.config import ConfigError
from avalon.rules import MAX_PLAYERS, MIN_PLAYERS, DEFAULT_PLAYERS
from avalon.web.manager import ALL_SEATS, DOWNLOADABLE, GAME_ID_RE, TERMINAL_STATUSES, GameManager, NewGameParams, now_iso

STATIC_DIR = Path(__file__).parent / "static"
HEARTBEAT_S = 15.0
MEDIA_TYPES = {".md": "text/markdown; charset=utf-8", ".jsonl": "application/x-ndjson; charset=utf-8", ".json": "application/json; charset=utf-8"}


class NewGameBody(BaseModel):
    seed: int | None = None
    thinking: bool = False
    model: str = Field(default="", max_length=80)
    random_players: bool = False
    random_delay_s: float = Field(default=1.5, ge=0, le=60)
    players: int = Field(default=DEFAULT_PLAYERS, ge=MIN_PLAYERS, le=MAX_PLAYERS)
    count: int = Field(default=1, ge=1, le=50)


def render_index() -> str:
    """入口页动态生成：脚本与样式地址带上前端文件的版本号，模块之间的相对引用经 import map 同样改走带版本号的地址。
    浏览器按地址缓存，前端文件一变地址就变，普通刷新即可拿到新代码，不必清缓存。"""
    version = static_version()
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    modules = {
        f"/static/{f.relative_to(STATIC_DIR).as_posix()}": f"/static/{f.relative_to(STATIC_DIR).as_posix()}?v={version}"
        for f in sorted(STATIC_DIR.rglob("*.js"))
    }
    import_map = f'<script type="importmap">{json.dumps({"imports": modules}, ensure_ascii=False)}</script>'
    html = html.replace('href="/static/app.css"', f'href="/static/app.css?v={version}"')
    html = html.replace('src="/static/app.js"', f'src="/static/app.js?v={version}"')
    return html.replace("<head>", f"<head>\n  {import_map}", 1)


def static_version() -> str:
    """前端文件的最新修改时间。页面每次切换画面时对比它，变了就自动刷新，拿到新脚本。"""
    return str(int(max((f.stat().st_mtime for f in STATIC_DIR.rglob("*") if f.is_file()), default=0)))


def sse(event: str, data: Any, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def create_app(manager: GameManager, *, heartbeat_s: float = HEARTBEAT_S) -> FastAPI:
    """heartbeat_s 是事件流无事可发时的心跳间隔，也是断线后服务端发现的最长延迟。"""
    app = FastAPI(title="阿瓦隆裁判席", docs_url=None, redoc_url=None)

    def valid_id(game_id: str) -> str:
        if not GAME_ID_RE.match(game_id):
            raise HTTPException(404, "没有这一局")
        return game_id

    def summary_or_404(game_id: str) -> dict[str, Any]:
        summary = manager.summary(valid_id(game_id))
        if summary is None:
            raise HTTPException(404, "没有这一局")
        return summary

    # ------------------------------------------------------------ 页面

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(render_index())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def no_cache_for_pages(request: Request, call_next):
        """页面与脚本每次都向服务端核对新旧，改完前端不必清缓存。"""
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # ------------------------------------------------------------ 列表与新开

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {**manager.defaults(), "static_version": static_version()}

    @app.get("/api/games")
    def list_games() -> dict[str, Any]:
        games = manager.list_games()
        return {"games": games, "stats": manager.stats(games), "server_now": now_iso(), **_capacity()}

    def _capacity() -> dict[str, int]:
        return {"max_concurrent": manager.max_concurrent, "running": manager.running_count()}

    @app.post("/api/games", status_code=201)
    def create_games(body: NewGameBody) -> dict[str, Any]:
        params = NewGameParams(
            seed=body.seed,
            thinking=body.thinking,
            model=body.model.strip(),
            random_players=body.random_players,
            random_delay_s=body.random_delay_s,
            players=body.players,
            count=body.count,
        )
        try:
            ids = manager.create(params)
        except ConfigError as e:
            raise HTTPException(400, str(e)) from e
        return {"ids": ids}

    # ------------------------------------------------------------ 单局

    @app.get("/api/games/{game_id}")
    def get_game(game_id: str) -> dict[str, Any]:
        return summary_or_404(game_id)

    @app.get("/api/games/{game_id}/events")
    def get_events(game_id: str, since: int = 0) -> dict[str, Any]:
        summary = summary_or_404(game_id)
        events = manager.events(game_id, max(0, since)) or []
        return {"game": summary, "events": events}

    @app.post("/api/games/{game_id}/pause")
    def pause(game_id: str) -> dict[str, Any]:
        return _control(game_id, manager.pause)

    @app.post("/api/games/{game_id}/resume")
    def resume(game_id: str) -> dict[str, Any]:
        return _control(game_id, manager.resume)

    @app.post("/api/games/{game_id}/terminate")
    def terminate(game_id: str) -> dict[str, Any]:
        return _control(game_id, manager.terminate)

    def _control(game_id: str, fn) -> dict[str, Any]:
        summary = fn(valid_id(game_id))
        if summary is None:
            if manager.summary(game_id) is not None:
                raise HTTPException(409, "这一局不在本服务进程里运行，无法操作")
            raise HTTPException(404, "没有这一局")
        return summary

    @app.get("/api/games/{game_id}/players/{pid}")
    def player_thread(game_id: str, pid: str) -> dict[str, Any]:
        if pid not in ALL_SEATS:
            raise HTTPException(404, "没有这个座位")
        summary = summary_or_404(game_id)
        if pid not in manager.seats_of(game_id):
            raise HTTPException(404, "这一局没有这个座位")
        messages = manager.player_thread(game_id, pid)
        return {"game": summary, "player": pid, "messages": messages or []}

    @app.get("/api/games/{game_id}/files/{name:path}")
    def get_file(game_id: str, name: str, download: int = 0) -> FileResponse:
        if name not in DOWNLOADABLE:
            raise HTTPException(404, "没有这个文件")
        if name.startswith("players/") and name.removeprefix("players/").removesuffix(".json") not in manager.seats_of(valid_id(game_id)):
            raise HTTPException(404, "这一局没有这个座位")
        path = manager.file(valid_id(game_id), name)
        if path is None:
            raise HTTPException(404, "文件尚未生成")
        media = MEDIA_TYPES.get(path.suffix, "application/octet-stream")
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{game_id}-{name.replace("/", "-")}"'
        return FileResponse(path, media_type=media, headers=headers)

    # ------------------------------------------------------------ 事件流

    limiter = anyio.CapacityLimiter(200)
    """事件流等待消息时占用的线程名额，与普通请求的线程池分开，几十个页面同时开着也不互相拖累。"""

    async def wait(q: queue.Queue) -> dict[str, Any] | None:
        """在线程里等一条消息，最多等一个心跳周期；浏览器断开时 anyio 取消这次等待，不必等线程返回。"""
        try:
            return await anyio.to_thread.run_sync(q.get, True, heartbeat_s, abandon_on_cancel=True, limiter=limiter)
        except queue.Empty:
            return None

    @app.get("/api/games/{game_id}/stream")
    def game_stream(game_id: str, request: Request, since: int = 0) -> StreamingResponse:
        summary_or_404(game_id)
        last_id = request.headers.get("last-event-id")
        if last_id and last_id.isdigit():
            since = int(last_id)
        return StreamingResponse(_game_events(game_id, since), media_type="text/event-stream", headers=_sse_headers())

    async def _game_events(game_id: str, since: int) -> AsyncIterator[str]:
        run = manager.get(game_id)
        q = run.subscribe() if run is not None else None
        last_seq = since
        try:
            for e in manager.events(game_id, since) or []:
                if e["seq"] > last_seq:
                    last_seq = e["seq"]
                    yield sse("game_event", e, e["seq"])
            summary = manager.summary(game_id)
            yield sse("status", summary)
            if q is None or (summary and summary["status"] in TERMINAL_STATUSES):
                # 已结束的局：只发一次全量，然后保持连接直到浏览器断开。
                while True:
                    yield ": keep-alive\n\n"
                    await anyio.sleep(heartbeat_s)
            while True:
                msg = await wait(q)
                if msg is None:
                    yield ": keep-alive\n\n"
                    continue
                if msg["type"] == "event":
                    e = msg["event"]
                    if e["seq"] > last_seq:
                        last_seq = e["seq"]
                        yield sse("game_event", e, e["seq"])
                elif msg["type"] == "status":
                    yield sse("status", msg["game"])
        finally:
            if run is not None and q is not None:
                run.unsubscribe(q)

    @app.get("/api/stream")
    def list_stream() -> StreamingResponse:
        return StreamingResponse(_list_events(), media_type="text/event-stream", headers=_sse_headers())

    async def _list_events() -> AsyncIterator[str]:
        q = manager.subscribe()
        try:
            games = manager.list_games()
            yield sse("games", {"games": games, "stats": manager.stats(games), "server_now": now_iso(), **_capacity()})
            while True:
                msg = await wait(q)
                if msg is None:
                    yield ": keep-alive\n\n"
                    continue
                if msg["type"] == "game":
                    yield sse("game", {"game": msg["game"], **_capacity()})
                elif msg["type"] == "removed":
                    yield sse("removed", {"id": msg["id"], **_capacity()})
        finally:
            manager.unsubscribe(q)

    def _sse_headers() -> dict[str, str]:
        return {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app

