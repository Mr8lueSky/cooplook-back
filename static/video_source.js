const MAX_FILE_SIZE = 5 * 1024 * 1024;

const ROOM_NAME_REG = "[а-яА-Яa-zA-Z ,./|\\?!:0-9]*";

const FROM_LINK = "from-link"
const FROM_TORRENT = "from-torrent"

let createFromTorrentElem = document.getElementById(FROM_TORRENT)
let createFromLinkElem = document.getElementById(FROM_LINK)
let selectSourceElem = document.getElementById("video-from")
let formElm = document.getElementById("roomForm")
let torrentUploadElm = document.getElementById("roomFile")
let roomNameElm = document.getElementById("roomName")

let sourcesToElements = {
        [FROM_LINK]: createFromLinkElem,
        [FROM_TORRENT]: createFromTorrentElem,

}



let selectSource = () => {
        console.log(`Selecting source ${selectSourceElem.value}!`)
        for (const [key, value] of Object.entries(sourcesToElements)) {
                if (key === selectSourceElem.value) {
                        value.hidden = false;
                        let elements = value.getElementsByTagName("input")
                        for (let i = 0; i < elements.length; i++) {
                                elements.item(i).disabled = false;
                        }

                        formElm.action = sourcesToLinks[key]

                } else {
                        let elements = value.getElementsByTagName("input")
                        for (let i = 0; i < elements.length; i++) {
                                elements.item(i).disabled = true;
                        }
                        value.hidden = true;
                }
        }
}



selectSourceElem.addEventListener("change", selectSource)
window.onload = function() {
        selectSource()
}


if (torrentUploadElm) {
        torrentUploadElm.addEventListener("input", () => {
                clearAlerts();
                if (torrentUploadElm.files[0].size >= MAX_FILE_SIZE) {
                        createAlert(`File size to big! Max is ${MAX_FILE_SIZE / 1024 / 1024} Mb.`);
                        torrentUploadElm.value = ''
                }
        })
}


if (roomNameElm) {
	roomNameElm.addEventListener("input", () => {
		roomNameElm.value = roomNameElm.value.match(ROOM_NAME_REG)[0];
	})
}
