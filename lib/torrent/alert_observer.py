from asyncio import sleep
from collections import defaultdict
from typing import Callable


from lib.logger import Logging
from lib.torrent.torrent import Alert, Torrent

OBSERVE_ALERTS_SLEEP = 0

AlertType = type[Alert]
NotifyAlert = Callable[[Alert], None]


class AlertObserver(Logging):
    def __init__(self, torrent: Torrent) -> None:
        self.alert_observers: defaultdict[AlertType, list[NotifyAlert]] = defaultdict(
            list
        )
        self.torrent: Torrent = torrent
        self.observe: bool = True

    async def observe_alerts(self):
        while self.observe:
            alerts = self.torrent.pop_alerts()
            for a in alerts:
                alert_type = type(a)
                self.logger.debug(f"Got alert: {a}")
                for observer in self.alert_observers[alert_type]:
                    observer(a)
            await sleep(OBSERVE_ALERTS_SLEEP)

    def cleanup(self):
        self.observe = False

    def add_alert_observer(self, alert_type: AlertType, observer: NotifyAlert):
        self.alert_observers[alert_type].append(observer)

    def remove_alert_observer(self, alert_type: AlertType, observer: NotifyAlert):
        self.alert_observers[alert_type].remove(observer)
