const PLAY = "pl"
const PAUSE = "pa"
const SET_CT = "sc"
const PEOPLE_COUNT = "pc"
const SUSPEND = "sp"
const UNSUSPEND = "up"
const FORCE_UNSUSPEND = "fu"
const RELOAD = "rl"
const CHANGE_FILE = "cf"

const MOE_S = 1;

let fi = 0;

let waiting = true;
let initial = true;

let sendOnConnect = [];

let ignorePlay = 0;
let ignorePause = 0;
let ignoreWaiting = 0;

let videoElem = document.getElementById("main-video");
videoElem.muted = true;

let deleteButton = document.getElementById("delete-btn")
let updateButton = document.getElementById("update-room")

let nameUpdateElm = document.getElementById("updated-name")
let imgLinkUpdateElm = document.getElementById("updated-img-link")
let peopleCountElem = document.getElementById("people-count");
let currentStatusElem = document.getElementById("current-status");
let videoAlertElem = document.getElementById("video-alert");
let selectFileElem = document.getElementById("select-file")
let videoContainer = document.getElementById("video-wrapper")

let currentStatus = "";



let cmdToStatus = {
        [PLAY]: "PLAY",
        [PAUSE]: "PAUSE",
        [SUSPEND]: "SUSPEND",
        [UNSUSPEND]: "UNSUSPEND"
};

let showOnOpen = [videoElem];



let setCurrTime = (currentTime) => {
        if (!waiting) ignoreWaiting += 1;;
        console.log(`Setting current time: ${ignoreWaiting}`)
        videoElem.currentTime = currentTime
}

function reloadVideo() {
        console.log("Reloading video!")
        videoElem.load();
	videoElem.src = `/files/${room_id}/${fi}`
        videoElem.currentTime = 0;
}


let selectFile = () => {
        let newFile = selectFileElem.value;
        console.log(`Selecting file ${newFile}!`)
        sendCommand(CHANGE_FILE, newFile)
        reloadVideo()
}

function sendStatus(status) {
        sendCommand(status, videoElem.currentTime)
}

function setStatus(newStatus, send = false) {
        if (!(newStatus in cmdToStatus)) {
                console.log(`Status doesn't exist: ${newStatus}`);
                return;
        }
        if (newStatus === currentStatus) {
                console.log(`Status is already ${currentStatus}`);
                return
        };
        console.log(`Changing status from ${currentStatus} to ${newStatus}`)

        if (newStatus === SUSPEND) videoAlertElem.textContent = "Waiting to load...";
        else videoAlertElem.textContent = "";
        currentStatus = newStatus;
        if (send) {
                sendCommand(newStatus, videoElem.currentTime)
        }
}


async function play_video() {
        if (!videoElem.paused) return;
        try {
                ignorePlay += 1;
                await videoElem.play();
                console.log(`Triggering play ${ignorePlay}`)
        } catch (err) {
                console.log(err)
                ignorePlay -= 1;
        }
}

async function pause_video() {
        if (videoElem.paused) return;
        videoElem.pause();
        ignorePause += 1
        console.log(`Triggering pause ${ignorePause}`)
}


videoElem.addEventListener("play", async () => {
        if (ignorePlay > 0) {
                ignorePlay -= 1;
                console.log(`Skipping play, left ${ignorePlay}`)
                return;
        }
        await pause_video()
        console.log("Play event")
        sendStatus(PLAY)
})

videoElem.addEventListener("pause", async () => {
        if (ignorePause > 0) {
                ignorePause -= 1;
                console.log(`Skipping pause, left ${ignorePause}`)
                return;
        }
        await play_video()
        console.log("Pause event")

        sendStatus(PAUSE)
})




let createSocket = () => {
        let websocket = new WebSocket(`/rooms/${room_id}/ws`);
        async function wsOnMessage(message) {
                let [cmd, arg] = message.data.split(' ')
                arg = parseFloat(arg)
                console.log(`Command rc: ${cmd}, current time: ${arg}`)
                if (cmd == PLAY) {
                        console.log("PLAY FROM SERVER")
                        setStatus(PLAY);
                        await play_video()
                } else if (cmd == PAUSE) {
                        setStatus(PAUSE);
                        console.log("PAUSE FROM SERVER")
                        await pause_video()
                } else if (cmd == SUSPEND) {
                        console.log("SUSPEND")
                        setStatus(SUSPEND);
                        await pause_video()
                } else if (cmd === UNSUSPEND) {
                        console.log("UNSUSPEND");
                        return;
                } else if (cmd == PEOPLE_COUNT) {
                        // peopleCountElem.textContent = arg;
                        return;
                } else if (cmd == CHANGE_FILE) {
			fi = arg;
                        reloadVideo();
                        return;
                }
                if (Math.abs(videoElem.currentTime - arg) > MOE_S)
                        setCurrTime(arg)

        }
        websocket.onclose = async () => {
                console.log("Socket closed.")
                showOnOpen.forEach(element => element.hidden = true);
        }
        websocket.onopen = async () => {
                console.log("Socket open.")
                showOnOpen.forEach(element => element.hidden = false);

        }
        websocket.onmessage = wsOnMessage;
        return websocket
}

showOnOpen.forEach(element => element.hidden = true);
let ws = createSocket();


let sendCommand = (cmd, data) => {
        console.log(`Sn: ${cmd} ${data}`)
        try {
                ws.send(`${cmd} ${data}`)
        } catch (exc) {
                console.error(`Caught error: ${exc}`)
        }
}

let deleteRoom = async () => {
        await fetch("", {
                method: "DELETE"
        })
        document.location.href = "/rooms"
}

let updateRoom = async () => {
        clearAlerts()
        await fetch("", {
                method: "PUT",
                headers: {
                        "Content-Type": "application/json"
                },
                body: JSON.stringify({
                        name: nameUpdateElm.value,
                        img_link: imgLinkUpdateElm.value
                })
        })
        await showAlerts()
}

videoElem.addEventListener("waiting", () => {
        waiting = true;
        if (ignoreWaiting) {
                console.log(`Ignore waiting! Left: ${ignoreWaiting}`)
                ignoreWaiting -= 1;
                return;
        }
        console.log("Set status SUSPEND from waiting event")
        sendStatus(SUSPEND)
})
videoElem.addEventListener("canplaythrough", () => {
        waiting = false;
        console.log("Set status UNSUSPEND from canplaythrough event")
        sendCommand(UNSUSPEND, videoElem.currentTime)
})



videoElem.addEventListener("error", (e) => {
        console.error(`Got error video error`)
	console.error(e)
})

if (navigator.getAutoplayPolicy == !undefined && (navigator.getAutoplayPolicy(videoElem) === "allowed-muted" ||
                navigator.getAutoplayPolicy(videoElem) === "disallowed")) {
        const newElement = document.createElement("h1");
        newElement.textContent = "Влючи автоплей, ублюдок"
        document.getElementsByTagName("body")[0].insertAdjacentElement("beforebegin", newElement)
}

// selectFileElem.addEventListener("change", selectFile)
deleteButton.addEventListener("click", deleteRoom)
// updateButton.addEventListener("click", updateRoom)
