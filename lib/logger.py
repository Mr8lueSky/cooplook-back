import logging


def create_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.FileHandler("logging.log", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s :%(levelname)s: |%(filename)s:%(lineno)d| [%(name)s] %(message)s"
            )
        )
        logger.addHandler(handler)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(handler.formatter)
        stream_handler.setLevel(logging.INFO)
        logger.addHandler(stream_handler)
        logger.setLevel(logging.DEBUG)
    return logger


class Logging:
    _logger: logging.Logger | None = None

    @property
    def logger(self) -> logging.Logger:
        if self._logger is None:
            self._logger = create_logger(self.__class__.__name__)
        return self._logger
