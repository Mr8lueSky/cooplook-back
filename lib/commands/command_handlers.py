from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import override

from lib.commands.client_commands import (ClientCommand, StateChangeClientCommand,
                                      client_commands)
from lib.logger import Logging
from lib.video_status.status_storage import StatusHandler
from schemas.user_schemas import UserRoomSchema


class CommandTypeHandler(ABC):
    handle_type: type[ClientCommand]

    @abstractmethod
    def handle(self, cmd: ClientCommand): ...


class StateChangeCommandsHandler(CommandTypeHandler):
    handle_type: type[ClientCommand] = StateChangeClientCommand

    def __init__(self, status_storage: StatusHandler) -> None:
        super().__init__()
        self.status_storage: StatusHandler = status_storage

    @override
    def handle(self, cmd: ClientCommand):
        if not isinstance(cmd, StateChangeClientCommand):
            raise TypeError(f"{self} can't handle {cmd}!")

        self.handle_status_change_cmd(cmd)

    def handle_status_change_cmd(self, cmd: StateChangeClientCommand):
        _ = cmd.handle(self.status_storage)


class CommandsGroupHandler(CommandTypeHandler, Logging):
    handle_type: type[ClientCommand] = ClientCommand

    def __init__(self, handlers_to_reg: Iterable[CommandTypeHandler]) -> None:
        super().__init__()
        self.cmd_type_to_handler: dict[type[ClientCommand], CommandTypeHandler] = {
            handler.handle_type: handler for handler in handlers_to_reg
        }

    def match_cmd_handler(self, cmd: ClientCommand):
        for cmd_type, handler in self.cmd_type_to_handler.items():
            if isinstance(cmd, cmd_type):
                return handler
        raise RuntimeError(f"Can not find handler for {cmd} command!")

    @override
    def handle(self, cmd: ClientCommand):
        handler = self.match_cmd_handler(cmd)
        handler.handle(cmd)

    def handle_str_cmd(self, cmd_str: str, by: UserRoomSchema):
        prefix, *args = cmd_str.split(" ")
        command = client_commands.get(prefix)
        if command is None:
            self.logger.error(f"Got unexpected command: {prefix}")
            raise RuntimeError(f"Unknown command {prefix}!")
        self.logger.debug(f"Handling {prefix} command with {command}")
        return self.handle(command.from_arguments(args, by.conn_id))
