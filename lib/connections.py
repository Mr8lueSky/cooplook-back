from asyncio import gather
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import count
from lib.logger import Logging

from fastapi import WebSocket

from lib.commands.server_commands import ServerCommand


@dataclass
class Connection(Logging):
    ws_conn: WebSocket

    async def accept(self):
        try:
            await self.ws_conn.accept()
        except Exception as err:
            raise RuntimeError(f"Raise in accept: {err}")

    async def recieve(self):
        return await self.ws_conn.receive_text()

    async def send(self, cmd: ServerCommand):
        try:
            await self.ws_conn.send_text(cmd.to_string())
        except Exception as exc:
            self.logger.debug(f"Got exc on send; cmd: {cmd}, exc: {type(exc)} {exc}")


@dataclass
class ConnectionsManager:
    conns: dict[int, Connection] = field(default_factory=dict)
    conn_id_iter: Iterator[int] = field(default_factory=count)

    async def send_to(self, conn_id: int, cmd: ServerCommand):
        if conn_id not in self.conns:
            raise RuntimeError(f"Unknown id:{conn_id}")
        conn = self.conns[conn_id]
        try:
            await conn.send(cmd)
        except Exception as exc:
            raise RuntimeError(f"It's here: {exc}")

    async def add_connection(self, conn: Connection) -> int:
        await conn.accept()
        conn_id = next(self.conn_id_iter)
        self.conns[conn_id] = conn
        return conn_id

    def remove_connection(self, conn_id: int):
        _ = self.conns.pop(conn_id)

    async def send_room(self, cmd: ServerCommand, exclude: list[int] | None = None):
        exclude = exclude or []
        _ = gather(
            *(
                conn.send(cmd)
                for conn_id, conn in self.conns.items()
                if conn_id not in exclude
            )
        )

    def conn_count(self) -> int:
        return len(self.conns)
