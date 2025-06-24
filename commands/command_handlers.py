from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import override

from commands.client_commands import (ClientCommand, StateChangeClientCommand,
                                      client_commands)
from logger import Logging
from video_status.status_storage import StatusStorage


class CommandTypeHandler(ABC):
    handle_type: type[ClientCommand]

    @abstractmethod
    def handle(self, cmd: ClientCommand): ...


class StatusChangeCommandsHandler(CommandTypeHandler):
    handle_type: type[ClientCommand] = StateChangeClientCommand

    def __init__(self, status_storage: StatusStorage) -> None:
        super().__init__()
        self.status_storage: StatusStorage = status_storage

    @override
    def handle(self, cmd: ClientCommand):
        if not isinstance(cmd, StateChangeClientCommand):
            raise TypeError(f"{self} can't handle {cmd}!")

        self.handle_status_change_cmd(cmd)

    def handle_status_change_cmd(self, cmd: StateChangeClientCommand):
        self.status_storage.set_status(cmd.handle_status(self.status_storage.status))


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

    def handle_str_cmd(self, cmd_str: str, by: int):
        prefix, *args = cmd_str.split(" ")
        command = client_commands.get(prefix)
        if command is None:
            self.logger.error(f"Got unexpected command: {prefix}")
            raise RuntimeError(f"Unknown command {prefix}!")
        self.logger.debug(f"Handling {prefix} command with {command}")
        return self.handle(command.from_arguments(args, by))
