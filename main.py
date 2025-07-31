from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from exception_handlers import register_exception_handlers
from lib.engine import create_users
from lib.room import RoomStorage, monitor_rooms
from routes.auth import auth_router
from routes.rooms import rooms_router
from config import ENV

app = FastAPI()

if ENV == "DEV":
    origins = ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_event_handler(
    "startup", monitor_rooms
)  # pyright: ignore[reportUnknownMemberType]
app.add_event_handler(
    "startup", create_users
)  # pyright: ignore[reportUnknownMemberType]
app.add_event_handler(
    "shutdown", RoomStorage.full_cleanup
)  # pyright: ignore[reportUnknownMemberType]

register_exception_handlers(app)

app.include_router(auth_router, prefix="/auth")
app.include_router(rooms_router, prefix="/rooms")
