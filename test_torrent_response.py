import asyncio
import os
from asyncio import sleep

import libtorrent as lt

from custom_responses import LoadingTorrentFileResponse
from main import PieceManager

TORRENT_FILE = "test.torrent"

result = open("result.mkv", 'wb')
expected = open("expected.mkv", 'rb')

# expected hash: 798490fb90ffea5ffe902f991fe04fa1
FILE_PATH = "torrents/Kijin Gentoushou - AniLibria [WEBRip 1080p]/Kijin_Gentosho_[02]_[AniLibria]_[WEBRip_1080p].mkv"
FILE_INDEX = 1
params = lt.session_params({
    # 'listen_interfaces': '0.0.0.0:6881',
})

session = lt.session(params)

ti = lt.torrent_info(TORRENT_FILE)
th = session.add_torrent({'ti': ti, 'save_path': 'torrents'})
th.prioritize_pieces((i, 0) for i in range(ti.files().num_pieces()))

size = ti.files().file_size(FILE_INDEX)

prs = ti.map_file(FILE_INDEX, 0, 0)
piece_start = prs.piece
th.prioritize_pieces((i, 0) for i in range(ti.files().num_pieces()))
th.piece_priority(piece_start, 7)


# class PieceManager:
#     def __init__(self, session):
#         self.piece_buffer = {}
#         self.piece_wait = {}
#         self.ses = session
#
#     async def get_piece(self, piece_id: int):
#         self.piece_wait[piece_id] = self.piece_wait.get(piece_id, 0) + 1
#         while piece_id not in self.piece_buffer:
#             alerts = self.ses.pop_alerts()
#             for a in alerts:
#                 if isinstance(a, lt.read_piece_alert):
#                     self.piece_buffer[piece_id] = a.buffer
#             await sleep(0.001)
#         buffer = self.piece_buffer[piece_id]
#         self.piece_wait[piece_id] -= 1
#         if not self.piece_wait[piece_id]:
#             self.piece_wait.pop(piece_id)
#             self.piece_buffer.pop(piece_id)
#         return buffer


async def download_range(start, end):
    async def send(data):
        nonlocal more_body, left
        if "headers" in data:
            print("Headers", data)
            return
        expected_body = expected.read(len(data['body']))
        result.write(data['body'])
        if expected_body != data['body']:
            with open("bad", 'wb') as file:
                file.write(data['body'])
            assert expected_body == data['body'], f"Data not matching! Left: {left}"
        if not more_body and data['more_body']:
            raise Exception("Bad, very bad")
        if not data['more_body']:
            more_body = False
        left -= len(data['body'])

    more_body = True
    expected.seek(start)
    left = end - start
    # t_start = time.time()
    print("Waiting for files")
    prior = th.get_piece_priorities()
    print("Priorities:", [(i, p) for i, p in enumerate(prior) if p], f"{left=}")
    while not os.path.isfile(FILE_PATH):
        await sleep(0.1)
    print("Starting")
    response = LoadingTorrentFileResponse(
        FILE_PATH,
        torrent_info=ti,
        torrent_handle=th,
        file_index=FILE_INDEX,
        piece_manager=PieceManager(session)
    )
    # send: Send, start: int, end: int, file_size: int, send_header_only: bool
    await response._handle_single_range(send, start, end, 0, False)
    # print("Finished in", time.time() - start)
    assert left == 0, f"Data is not matching in size: {left}"
    assert not more_body, f"There are still more body!"


async def main():
    await download_range(0, size)
    await download_range(1000, 1000000)
    await download_range(123456, 7486720)
    await download_range(0, 9469952)
    await download_range(1035272192, 1035305458)


if __name__ == '__main__':
    asyncio.run(main())
