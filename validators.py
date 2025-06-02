from pathlib import Path
import libtorrent as lt

torrent_type = Path | str | bytes

def is_valid_torrent(torrent: torrent_type):
    ans = False
    try:
        lt.torrent_info(torrent)
        ans = True
    except Exception:
        ...
    return ans
