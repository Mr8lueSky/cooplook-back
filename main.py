from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ENV
from exception_handlers import register_exception_handlers
from lib.engine import create_users
from lib.room import RoomStorage, monitor_rooms
from routes.auth import auth_router
from routes.rooms import rooms_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_users()
    monitor_rooms()
    yield
    await RoomStorage.full_cleanup()


app = FastAPI(lifespan=lifespan)

if ENV == "DEV":
    origins = ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(rooms_router)
