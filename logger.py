import logging


class Logging:
    _logger: None | logging.Logger = None

    @property
    def logger(self):
        if self._logger is None:
            self._logger = logging.getLogger(self.__class__.__name__)
            logging.basicConfig(
                filename="logging.log",
                encoding="utf-8",
                level=logging.DEBUG,
               format="%(asctime)s :%(levelname)s: [%(name)s] %(message)s",
            )
        return self._logger
