import asyncio
from asyncio import Lock, wait_for
from dataclasses import dataclass, field
from time import time
from traceback import format_exception
from uuid import UUID

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from cmds import Commands, VideoStatus
from config import ROOM_INACTIVITY_PERIOD
from engine import async_session_maker
from logger import Logging, create_logger
from models.room_model import RoomModel, enum_to_source
from video_sources import VideoSource

MOE = 1
rooms: dict[UUID, "RoomInfo"] = {}
lock = Lock()
monitor_logger = create_logger("RoomMonitor")


@dataclass
class RoomInfo(Logging):
    video_source: VideoSource
    name: str
    room_id: UUID
    prev_status: None | VideoStatus = None
    wss: dict[int, WebSocket] = field(default_factory=dict)
    last_ws_id: int = 0
    _current_time: float = 0
    status: VideoStatus = VideoStatus.PAUSE
    last_change: float = field(default_factory=time)
    suspend_by: set[int] = field(default_factory=set)
    last_leave_ts: float = field(default_factory=time)

    @classmethod
    def from_model(cls, model: RoomModel) -> "RoomInfo":
        vs_cls: type[VideoSource] = enum_to_source[model.video_source]
        r = RoomInfo(
            vs_cls(model.video_source_data, model.last_file_ind, model.room_id),
            model.name,
            model.room_id,
            _current_time=model.last_watch_ts,
        )
        r.video_source.start()
        return r

    async def set_new_file(self, new_fi_str: str, ws_id: int) -> bool:
        new_fi = int(new_fi_str)
        if not self.video_source.set_current_fi(new_fi):
            return False
        await self.send_room(Commands.change_file_cmd(new_fi), ws_id)
        asyncio.gather(
                *(self.initial(ws, ws_id) for ws_id, ws in self.wss.items()))
        # await self.change_status(VideoStatus.SUSPEND, ws_id)
        await self.handle_set_time(str(0), ws_id, cancel_reqs=True)

        
        return True

    def get_available_files(self):
        return self.video_source.get_available_files()

    async def send_to(self, msg: str, to: int):
        try:
            if to in self.wss:
                await self.wss[to].send_text(msg)
        except RuntimeError:
            await self.handle_leave(to)

    async def send_room(self, msg: str, by: int = -1):
        self.logger.debug(f"Sn room {msg}, {by}")
        await asyncio.gather(
            *(self.send_to(msg, ws_id) for ws_id in self.wss.keys() if ws_id != by)
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

    async def handle_susp_unsusp(self, cmd: Commands, ts_str: str, by: int):
        if cmd == Commands.SUSPEND:
            self.suspend_by.add(by)
            if not self.status == VideoStatus.SUSPEND:
                await self.change_status(VideoStatus.SUSPEND, -1)

        if cmd == Commands.UNSUSPEND and by in self.suspend_by:
            self.suspend_by.remove(by)

        if not self.suspend_by and self.status == VideoStatus.SUSPEND:
            await self.handle_set_time(ts_str, by)
            new_status = self.prev_status or VideoStatus.PLAY
            await self.send_room(Commands.unsuspend_cmd(self.current_time))
            await self.change_status(new_status, -1)

    async def handle_ping(self, ts_str: str, to: int):
        ts = float(ts_str)
        if not (ts - MOE <= self.current_time <= ts + MOE):
            await self.send_to(Commands.set_time_cmd(self.current_time), to)

    async def handle_set_time(self, ts_str: str, by: int, cancel_reqs: bool = False):
        ts = float(ts_str)
        self.logger.info(f"Set current time from {self._current_time} to {ts}")
        self._current_time = ts
        self.last_change = time()
        if cancel_reqs:
            self.logger.debug("Canceling requests because time is changing")
            self.video_source.cancel_current_requests()
        await self.send_room(Commands.set_time_cmd(ts), by)
        await self.suspend_by_all(ts_str)

    async def suspend_by_all(self, ts_str: str):
        for i in self.wss.keys():
            await self.handle_susp_unsusp(Commands.SUSPEND, ts_str, i)
    
    async def handle_cmd(self, data: str, ws_id: int):
        self.logger.debug(f"Rc: {ws_id}, {data}")
        cmd, arg = data.split(" ")
        cmd = Commands(cmd)
        if cmd == Commands.PING:
            await self.handle_ping(arg, ws_id)
            return
        elif cmd == Commands.PLAY or cmd == Commands.PAUSE:
            await self.handle_play_pause(cmd, ws_id)
        elif cmd == Commands.SUSPEND or cmd == Commands.UNSUSPEND:
            await self.handle_susp_unsusp(cmd, arg, ws_id)
        elif cmd == Commands.SET_CT:
            await self.handle_set_time(arg, ws_id)
        elif cmd == Commands.CHANGE_FILE:
            await self.set_new_file(arg, ws_id)
        async with async_session_maker.begin() as session:
            await RoomModel.update(
                session, self.room_id, self.current_time, self.video_source.fi
            )

    async def handle_leave(self, ws_id: int):
        self.wss.pop(ws_id, None)
        if ws_id in self.suspend_by:
            await self.handle_susp_unsusp(Commands.UNSUSPEND, str(self.current_time), ws_id)
        await self.handle_play_pause(Commands.PAUSE, -1)
        await self.send_room(Commands.people_count_cmd(len(self.wss)))
        self.last_leave_ts = time()

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
        await self.handle_susp_unsusp(Commands.SUSPEND, str(self.current_time), ws_id)
        await self.send_room(Commands.people_count_cmd(len(self.wss)), -1)

    async def cleanup(self):
        self.video_source.cancel_current_requests()
        self.video_source.cleanup()


async def get_room(session: AsyncSession, room_id: UUID) -> RoomInfo:
    async with lock:
        if room_id not in rooms:
            room_model = await RoomModel.get_room_id(session, room_id)
            rooms[room_id] = RoomInfo.from_model(room_model)
    return rooms[room_id]


async def _monitor_rooms():
    while True:
        await asyncio.sleep(60)
        monitor_logger.info("Starting room cleanup")
        for room_id, room in tuple(rooms.items()):
            async with lock:
                if (
                    len(room.wss)
                    or time() - room.last_leave_ts < ROOM_INACTIVITY_PERIOD
                ):
                    monitor_logger.debug(
                        f"Skipping room {room_id}. "
                        f"Time from last leave: {time() - room.last_leave_ts}, "
                        f"people count: {len(room.wss)}"
                    )
                    continue
                room = rooms.pop(room_id)
            await room.cleanup()
            monitor_logger.debug(f"Cleaned room {room_id}")
            await asyncio.sleep(0)
        monitor_logger.info("Room cleanup finished")

async def monitor_rooms():
    asyncio.create_task(_monitor_rooms())
