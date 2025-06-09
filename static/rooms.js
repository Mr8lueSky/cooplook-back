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
let formElm = document.getElementById("create-form")

let sourcesToElements = {
        [FROM_LINK]: createFromLinkElem,
        [FROM_TORRENT]: createFromTorrentElem,
}

let sourcesToLinks = {
        [FROM_LINK]: FROM_LINK_URL,
        [FROM_TORRENT]: FROM_TORRENT_URL
}

let allowedChrRe = new RegExp("[a-zA-Z ,./|\\?!:0-9]*");


let validateRoomName = (roomName) => {
        let matchRes = roomName.match(allowedChrRe);
        return matchRes.length === 1 && matchRes[0].length === roomName.length &&
                3 < roomName.length && roomName.length < 32
}

let selectSource = () => {
        console.log(`Selecting source ${selectSourceElem.value}!`)
        for (const [key, value] of Object.entries(sourcesToElements)) {
                if (key === selectSourceElem.value) {
                        value.hidden = false;
                        formElm.action = sourcesToLinks[key]
                } else value.hidden = true;
        }
}


window.onload = function() {
        selectSource()
}

formElm.onsubmit = (event) => {
        console.log(event.formData)
        event.cancel()
}

selectSourceElem.addEventListener("change", selectSource)
