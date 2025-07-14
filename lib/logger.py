import logging


def create_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logging.basicConfig(
        filename="logging.log",
        encoding="utf-8",
        level=logging.DEBUG,
        format="%(asctime)s :%(levelname)s: [%(name)s] %(message)s",
    )
    return logger


class Logging:
    _logger: None | logging.Logger = None

    @property
    def logger(self):
        if self._logger is None:
            self._logger = create_logger(self.__class__.__name__)
        return self._logger
