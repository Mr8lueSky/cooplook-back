import asyncio
import re
from asyncio import wait_for
from dataclasses import dataclass, field
from time import time
from traceback import format_exception
from uuid import UUID
from starlette.websockets import WebSocketDisconnect
from fastapi import WebSocket

from cmds import VideoStatus, Commands
from logger import Logging
from video_sources import VideoSource

MOE = 1


@dataclass
class RoomInfo(Logging):
    room_id: UUID
    video_source: VideoSource
    name: str = field(
        metadata=dict(
            validate=lambda d: 4 <= len(d) <= 32 and re.fullmatch(r"[a-zA-Z0-9]*", d)
        )
    )
    prev_status: None | VideoStatus = None
    wss: dict[int, WebSocket] = field(default_factory=dict)
    last_ws_id: int = 0
    _current_time: float = 0
    status: VideoStatus = VideoStatus.PAUSE
    last_change: float = field(default_factory=time)
    suspend_by: set[int] = field(default_factory=set)

    def for_temp(self):
        return {
            "room_id": self.room_id,
            "video": self.video_source.get_player_src(self.room_id),
            "room_name": self.name,
        }

    async def send_to(self, msg: str, to: int):
        await self.wss[to].send_text(msg)

    async def send_room(self, msg: str, by: int = -1):
        self.logger.debug(f"Sn room {msg}, {by}")
        await asyncio.gather(
            *(ws.send_text(msg) for ws_id, ws in self.wss.items() if ws_id != by)
        )

    async def change_status(self, new_status: VideoStatus, by: int):
        self.logger.info(f"Changing status to {new_status}")
        if self.status == new_status:
            return
        self._current_time = self.current_time
        self.prev_status = self.status
        self.status = new_status
        self.last_change = time()
        await self.send_current_status(by)

    async def send_current_status(self, by: int):
        await self.send_room(f"{self.status.value} {self.current_time}", by)

    async def handle_play_pause(self, cmd: Commands, by: int):
        if self.status == VideoStatus.SUSPEND:
            return
        if self.status.value != cmd.value:
            await self.change_status(VideoStatus(cmd), by)

    async def handle_susp_unsusp(self, cmd: Commands, ts: float, by: int):
        if cmd == Commands.SUSPEND:
            self.suspend_by.add(by)
            if not self.status == VideoStatus.SUSPEND:
                await self.change_status(VideoStatus.SUSPEND, -1)

        if cmd == Commands.UNSUSPEND and by in self.suspend_by:
            self.suspend_by.remove(by)

        if not self.suspend_by and self.status == VideoStatus.SUSPEND:
            await self.handle_set_time(ts, by)
            new_status = self.prev_status or VideoStatus.PLAY
            await self.send_room(Commands.unsuspend_cmd(self.current_time))
            await self.change_status(new_status, -1)

    async def handle_ping(self, ts: float, to: int):
        if not (ts - MOE <= self.current_time <= ts + MOE):
            await self.send_to(Commands.set_time_cmd(self.current_time), to)

    async def handle_set_time(self, ts: float, by: int):
        self.logger.info(f"Set current time from {self._current_time} to {ts}")
        self._current_time = ts
        self.last_change = time()
        self.video_source.cancel()
        await self.send_room(Commands.set_time_cmd(ts), by)
        await self.suspend_by_all(ts)

    async def suspend_by_all(self, ts: float):
        for i in self.wss.keys():
            await self.handle_susp_unsusp(Commands.SUSPEND, ts, i)

    async def handle_cmd(self, data: str, ws_id: int):
        self.logger.debug(f"Rc: {ws_id}, {data}")
        cmd, ts = data.split(" ")
        ts = float(ts)
        cmd = Commands(cmd)
        if cmd == Commands.PING:
            await self.handle_ping(ts, ws_id)
        elif cmd == Commands.PLAY or cmd == Commands.PAUSE:
            await self.handle_play_pause(cmd, ws_id)
        elif cmd == Commands.SUSPEND or cmd == Commands.UNSUSPEND:
            await self.handle_susp_unsusp(cmd, ts, ws_id)
        elif cmd == Commands.SET_CT:
            await self.handle_set_time(ts, ws_id)

    async def handle_leave(self, ws_id: int):
        self.wss.pop(ws_id, None)
        if ws_id in self.suspend_by:
            await self.handle_susp_unsusp(Commands.UNSUSPEND, self.current_time, ws_id)
        await self.handle_play_pause(Commands.PAUSE, -1)
        await self.send_room(Commands.people_count_cmd(len(self.wss)))

    async def handle_client(self, websocket: WebSocket):
        ws_id = self.last_ws_id
        self.last_ws_id += 1
        try:
            await self.initial(websocket, ws_id)
            self.logger.info(f"Client {ws_id} connected")
            while True:
                try:
                    data = await wait_for(websocket.receive_text(), MOE)
                    await self.handle_cmd(data, ws_id)
                except TimeoutError:
                    if self.status != VideoStatus.PLAY:
                        continue
                    self.logger.info(f"Timeout for {ws_id}")
                    await self.change_status(VideoStatus.SUSPEND, ws_id)
        except WebSocketDisconnect:
            self.logger.info(f"User {ws_id} disconnected")
        except Exception as exc:
            self.logger.error("\n".join(format_exception(exc)))
        await self.handle_leave(ws_id)

    @property
    def current_time(self):
        if self.status == VideoStatus.PLAY:
            return self._current_time + time() - self.last_change
        return self._current_time

    async def initial(self, ws: WebSocket, ws_id: int):
        self.wss[ws_id] = ws
        await ws.accept()
        await self.send_to(Commands.set_time_cmd(self.current_time), ws_id)
        self.prev_status = VideoStatus.PAUSE
        await self.handle_susp_unsusp(Commands.SUSPEND, self.current_time, ws_id)
        await self.send_room(Commands.people_count_cmd(len(self.wss)), -1)
