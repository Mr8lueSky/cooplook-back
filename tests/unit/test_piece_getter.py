import asyncio
from dataclasses import dataclass

import pytest

import lib.torrent.piece_getter as pg_module
from lib.torrent.piece_getter import PieceGetter


class FakeErrorCode:
    def __init__(self, value: int) -> None:
        self._value = value

    def value(self) -> int:
        return self._value


@dataclass
class FakeReadPieceAlert:
    piece: int
    buffer: bytes | None
    size: int
    error: FakeErrorCode


class FakeTorrent:
    def __init__(self) -> None:
        self.have_pieces: set[int] = set()
        self.read_piece_calls: list[int] = []
        self.deadline_calls: list[tuple[int, int, int]] = []
        self.priorities: dict[int, int] = {}

    def have_piece(self, piece_id: int) -> bool:
        return piece_id in self.have_pieces

    def read_piece(self, piece_id: int) -> None:
        self.read_piece_calls.append(piece_id)

    def set_piece_deadline(self, piece_id: int, deadline_s: int, flags: int = 0) -> None:
        self.deadline_calls.append((piece_id, deadline_s, flags))

    def get_piece_priority(self, piece_id: int) -> int:
        return self.priorities.get(piece_id, 0)


class FakeAlertObserver:
    def __init__(self) -> None:
        self.observers: dict = {}

    def add_alert_observer(self, alert_type, observer) -> None:
        self.observers[alert_type] = observer

    def deliver(self, alert: FakeReadPieceAlert) -> None:
        self.observers[pg_module.lt.read_piece_alert](alert)


@pytest.fixture
def setup():
    torrent = FakeTorrent()
    observer = FakeAlertObserver()
    original = pg_module.ReadPieceAlert
    pg_module.ReadPieceAlert = FakeReadPieceAlert
    getter = PieceGetter(torrent, observer)
    yield torrent, observer, getter
    pg_module.ReadPieceAlert = original


def _succeed(observer, piece_id, data=b"piece-data"):
    observer.deliver(
        FakeReadPieceAlert(
            piece=piece_id, buffer=data, size=len(data), error=FakeErrorCode(0)
        )
    )


def _fail(observer, piece_id):
    observer.deliver(
        FakeReadPieceAlert(
            piece=piece_id, buffer=None, size=0, error=FakeErrorCode(1)
        )
    )


def test_deadline_set_once_for_many_waiters(setup):
    torrent, observer, getter = setup
    torrent.have_pieces.add(910)

    async def scenario():
        async def get_after_require():
            getter.require_piece(910)
            return await getter.get_piece(910)

        tasks = [asyncio.ensure_future(get_after_require()) for _ in range(3)]
        await asyncio.sleep(0.05)
        _succeed(observer, 910, b"data-910")
        results = await asyncio.gather(*tasks)
        assert results == [b"data-910", b"data-910", b"data-910"]
        deadline_calls_for_910 = [c for c in torrent.deadline_calls if c[0] == 910]
        assert len(deadline_calls_for_910) == 1, (
            f"Expected 1 set_piece_deadline call for piece 910, got {len(deadline_calls_for_910)}"
        )
        assert len(torrent.read_piece_calls) == 0, (
            "read_piece should never be called directly"
        )

    asyncio.run(scenario())


def test_failed_alert_does_not_poison_buffer(setup):
    _, observer, getter = setup
    getter.torrent.have_pieces.add(910)

    async def scenario():
        getter.require_piece(910)
        task = asyncio.ensure_future(getter.get_piece(910))
        await asyncio.sleep(0.05)
        _fail(observer, 910)
        assert not getter.piece_buffer.get(910), "Failed alert poisoned piece_buffer"
        _succeed(observer, 910, b"real-data")
        result = await asyncio.wait_for(task, timeout=5)
        assert result == b"real-data"

    asyncio.run(scenario())


def test_cancellation_does_not_break_others(setup):
    _, observer, getter = setup
    getter.torrent.have_pieces.add(910)

    async def scenario():
        for _ in range(3):
            getter.require_piece(910)

        async def get_910():
            return await getter.get_piece(910)

        t1 = asyncio.ensure_future(get_910())
        t2 = asyncio.ensure_future(get_910())
        t3 = asyncio.ensure_future(get_910())
        await asyncio.sleep(0.05)
        t2.cancel()
        try:
            await t2
        except asyncio.CancelledError:
            pass
        _succeed(observer, 910, b"survived")
        r1 = await asyncio.wait_for(t1, timeout=5)
        r3 = await asyncio.wait_for(t3, timeout=5)
        assert r1 == b"survived"
        assert r3 == b"survived"

    asyncio.run(scenario())


def test_lru_avoids_reread(setup):
    _, observer, getter = setup
    getter.torrent.have_pieces.add(910)

    async def scenario():
        getter.require_piece(910)
        t1 = asyncio.ensure_future(getter.get_piece(910))
        await asyncio.sleep(0.05)
        _succeed(observer, 910, b"cached")
        await asyncio.wait_for(t1, timeout=5)
        alerts_before = len(getter.torrent.read_piece_calls)
        getter.require_piece(910)
        result = await asyncio.wait_for(getter.get_piece(910), timeout=5)
        assert result == b"cached"
        assert len(getter.torrent.read_piece_calls) == alerts_before, (
            "LRU hit should not trigger a read_piece call"
        )

    asyncio.run(scenario())


def test_lru_eviction_at_capacity(setup):
    torrent, observer, getter = setup

    async def scenario():
        for pid in range(pg_module.PIECE_CACHE_SIZE + 5):
            torrent.have_pieces.add(pid)
            getter.require_piece(pid)
            task = asyncio.ensure_future(getter.get_piece(pid))
            await asyncio.sleep(0.01)
            _succeed(observer, pid, f"p{pid}".encode())
            await asyncio.wait_for(task, timeout=5)
            getter.not_require_piece(pid)
        assert len(getter.piece_cache) <= pg_module.PIECE_CACHE_SIZE, (
            f"Cache exceeded capacity: {len(getter.piece_cache)}"
        )
        assert 0 not in getter.piece_cache, "Oldest entry should have been evicted"
        assert pg_module.PIECE_CACHE_SIZE + 4 in getter.piece_cache, (
            "Newest entry should be present"
        )

    asyncio.run(scenario())


def test_failed_alert_does_not_block_next_waiter(setup):
    _, observer, getter = setup
    getter.torrent.have_pieces.add(910)

    async def scenario():
        getter.require_piece(910)
        t1 = asyncio.ensure_future(getter.get_piece(910))
        await asyncio.sleep(0.05)
        t1.cancel()
        try:
            await t1
        except asyncio.CancelledError:
            pass
        _fail(observer, 910)
        assert 910 not in getter.piece_wait_count, (
            "All waiters cancelled, count should be 0"
        )
        getter.require_piece(910)
        t2 = asyncio.ensure_future(getter.get_piece(910))
        await asyncio.sleep(0.05)
        _succeed(observer, 910, b"second-try")
        result = await asyncio.wait_for(t2, timeout=5)
        assert result == b"second-try"

    asyncio.run(scenario())


def test_alert_cached_even_with_no_waiters(setup):
    _, observer, getter = setup
    getter.torrent.have_pieces.add(910)

    async def scenario():
        getter.require_piece(910)
        task = asyncio.ensure_future(getter.get_piece(910))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert 910 not in getter.piece_wait_count, (
            "All waiters cancelled, count should be 0"
        )
        _succeed(observer, 910, b"orphaned-data")
        assert 910 in getter.piece_cache, (
            "Successful alert should be cached even with no active waiters"
        )
        assert getter.piece_cache[910] == b"orphaned-data"
        getter.require_piece(910)
        alerts_before = len(getter.torrent.read_piece_calls)
        result = await asyncio.wait_for(getter.get_piece(910), timeout=5)
        assert result == b"orphaned-data"
        assert len(getter.torrent.read_piece_calls) == alerts_before, (
            "New caller should hit the cache, not trigger a read_piece"
        )

    asyncio.run(scenario())