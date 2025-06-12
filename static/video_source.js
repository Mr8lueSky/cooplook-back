const FROM_LINK = "from-link"
const FROM_TORRENT = "from-torrent"


let createFromTorrentElem = document.getElementById(FROM_TORRENT)
let createFromLinkElem = document.getElementById(FROM_LINK)
let selectSourceElem = document.getElementById("video-from")
let formElm = document.getElementById("create-form")



let sourcesToElements = {
        [FROM_LINK]: createFromLinkElem,
        [FROM_TORRENT]: createFromTorrentElem,
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



selectSourceElem.addEventListener("change", selectSource)
window.onload = function() {
        selectSource()
}
