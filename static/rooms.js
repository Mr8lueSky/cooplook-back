const FROM_LINK = "from-link"
const FROM_TORRENT = "from-torrent"

const FROM_LINK_URL = "/rooms/from_link";
const FROM_TORRENT_URL = "/rooms/from_torrent";


let createFromTorrentElem = document.getElementById(FROM_TORRENT)
let createFromLinkElem = document.getElementById(FROM_LINK)
let selectSourceElem = document.getElementById("video-from")
let createRoomBt = document.getElementById("create-room")
let roomNameElm = document.getElementById("room-name")
let torrentFileElm = document.getElementById("torrent-file")
let linkElm = document.getElementById("video-link")
let alertsElm = document.getElementById("alerts")

let sourcesToElements = {
        [FROM_LINK]: createFromLinkElem,
        [FROM_TORRENT]: createFromTorrentElem,
}

let sourcesToLinks = {
        [FROM_LINK]: FROM_LINK_URL,
        [FROM_TORRENT]: FROM_TORRENT_URL
}

let allowedChrRe = new RegExp("[a-zA-Z ,./|\\?!:0-9]*");

let showAlert = (msg) => {
        alertsElm.textContent = msg
}

let clearAlert = () => {
        alertsElm.textContent = ""
}

let validateRoomName = (roomName) => {
        let matchRes = roomName.match(allowedChrRe);
        return matchRes.length === 1 && matchRes[0].length === roomName.length &&
                3 < roomName.length && roomName.length < 32
}

let selectSource = () => {
        console.log("Selecting source!")
        for (const [key, value] of Object.entries(sourcesToElements)) {
                console.log(key, value)
                if (key === selectSourceElem.value) value.hidden = false;
                else value.hidden = true;
        }
}

let onCreateRoomBtClick = async () => {
        clearAlert();
        let roomName = roomNameElm.value;
        if (!validateRoomName(roomName)) {
                showAlert("Length of a name should be between 4 and 32. Also don't use any special characters!");
                return;
        }

        let videoSource = selectSourceElem.value;
        let url = sourcesToLinks[videoSource];
        let data = new FormData();
        data.append("name", roomName)
        if (videoSource === FROM_LINK) {
                if (linkElm.value.length < 4) {
                        showAlert("Link must be at least 4 characters long")
                        return;
                }
                data.append("link", linkElm.value)
        } else if (videoSource === FROM_TORRENT) {
                if (torrentFileElm.files.length < 1) {
                        showAlert("Upload torrent file first")
                }
                data.append("torrent_file", torrentFileElm.files[0])
        }
        try {
                const resp = await fetch(url, {
                        method: "POST",
                        body: data,
                })

                const respJson = await resp.json();
                if (!resp.ok) {
                        showAlert(JSON.stringify(respJson))
                        return;
                }
                document.location.pathname = `/rooms/${respJson['room_id']}`

        } catch (exc) {
                showAlert(exc);
                return
        }
}

selectSource()

selectSourceElem.addEventListener("change", selectSource)
createRoomBt.addEventListener("click", onCreateRoomBtClick)
