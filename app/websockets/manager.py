import asyncio
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder


class ConnectionManager:
    """Rooms: order:<id>, restaurant:<owner_user_id>, partner:<user_id>, customer:<user_id>, admin."""

    def __init__(self):
        self.rooms: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop):
        self.loop = loop

    async def connect(self, room: str, ws: WebSocket):
        await ws.accept()
        self.rooms[room].add(ws)

    def disconnect(self, room: str, ws: WebSocket):
        conns = self.rooms.get(room)
        if conns is not None:
            conns.discard(ws)
            if not conns:
                self.rooms.pop(room, None)

    async def broadcast(self, room: str, message: dict):
        for ws in list(self.rooms.get(room, ())):
            try:
                await ws.send_json(message)
            except Exception:
                # dead connection: drop it silently
                self.disconnect(room, ws)

    def publish(self, room: str, message: dict):
        """Thread-safe: callable from sync endpoints and scheduler threads."""
        loop = self.loop
        if loop is None or loop.is_closed() or room not in self.rooms:
            return
        data = jsonable_encoder(message)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            loop.create_task(self.broadcast(room, data))
        else:
            asyncio.run_coroutine_threadsafe(self.broadcast(room, data), loop)


manager = ConnectionManager()
