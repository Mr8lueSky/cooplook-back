const PLAY = "pl"
const PAUSE = "pa"
const PING = "pi"
const SET_CT = "sc"
const PEOPLE_COUNT = "pc"
const SUSPEND = "sp"
const UNSUSPEND = "up"
const FORCE_UNSUSPEND = "fu"
const RELOAD = "rl"
const CHANGE_FILE = "cf"

let suspend = false;
let initial = true;
let last_ts = 0;

let ignorePlay = 0;
let ignorePause = 0;

let videoElem = document.getElementById("video");
videoElem.muted = true;

let fuButton = document.getElementById("force-uns")
let fsButton = document.getElementById("force-sus")

let peopleCountElem = document.getElementById("people-count");
let currentStatusElem = document.getElementById("current-status");
let alertElem = document.getElementById("alert");
let selectFileElem = document.getElementById("select-file")
let videoContainer = document.getElementById("video-wrapper")

let currentStatus = "";

let cmdToStatus = {
        [PLAY]: "PLAY",
        [PAUSE]: "PAUSE",
        [SUSPEND]: "SUSPEND",
};

let showOnOpen = [selectFileElem, videoElem];

function reloadVideo() {
        videoElem.load();
	videoElem.currentTime = 0;
        // ws.close()
        // ws = createSocket()
	// window.location.reload()
}
let selectFile = (event) => {
        let newFile = selectFileElem.value;
        console.log(`Selecting file ${newFile}!`)
	sendCommand(CHANGE_FILE,newFile)
	reloadVideo()
}



function setStatus(newStatus) {
        if (!(newStatus in cmdToStatus)) {
                console.log(`Status doesn't exist: ${newStatus}`);
                return;
        }
        if (newStatus === UNSUSPEND) {
                console.log("Unsuspending");
                currentStatus = "";
                return;
        }
        if (newStatus === currentStatus) return;
        if (newStatus === PLAY || newStatus === PAUSE) {
                if (suspend) return;
        }
        console.log(`Changing status from ${currentStatus} to ${newStatus}`)

        if (newStatus === SUSPEND) alertElem.textContent = "Waiting to load...";
        else alertElem.textContent = "";

        currentStatusElem.textContent = cmdToStatus[newStatus];
        currentStatus = newStatus;
}

setStatus(SUSPEND);

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
        if (suspend) {
                await pause_video()
                return;
        }
        if (ignorePlay > 0) {
                ignorePlay -= 1;
                console.log(`Skipping play, left ${ignorePlay}`)
                return;
        }
        sendCommand(PLAY, videoElem.currentTime)
        setStatus(PLAY);
        console.log("Play event")
})

videoElem.addEventListener("pause", async () => {
        if (ignorePause > 0) {
                ignorePause -= 1;
                console.log(`Skipping pause, left ${ignorePause}`)
                return;
        }
        sendCommand(PAUSE, videoElem.currentTime)
        setStatus(PAUSE);
        console.log("Pause event")
})




let createSocket = () => {
        let websocket = new WebSocket(`/rooms/${room_id}/ws`);
        async function wsOnMessage(message) {
                let [cmd, arg] = message.data.split(' ')
                arg = parseFloat(arg)
                console.log(`Command rc: ${cmd}, current time: ${arg}`)
                if (cmd == SET_CT) {
                        videoElem.currentTime = arg;
                        last_ts = arg;
                } else if (cmd == PLAY) {
                        console.log("PLAY FROM SERVER")
                        setStatus(PLAY);
                        videoElem.currentTime = arg;
                        await play_video()
                } else if (cmd == PAUSE) {
                        setStatus(PAUSE);
                        console.log("PAUSE FROM SERVER")
                        videoElem.currentTime = arg;
                        await pause_video()
                } else if (cmd == SUSPEND) {
                        console.log("SUSPEND")
                        setStatus(SUSPEND);
                        await pause_video()
                        suspend = true;
                } else if (cmd == UNSUSPEND) {
                        console.log("UNSUSPEND")
                        suspend = false;
                } else if (cmd == PEOPLE_COUNT) {
                        peopleCountElem.textContent = arg;
                        return;
                } else if (cmd == RELOAD) {
                        window.location.reload();
                        return;
                } else if (cmd == CHANGE_FILE) {
			reloadVideo();
			selectFileElem.selectedIndex = arg;
			return;
		}

                videoElem.currentTime = arg;
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




videoElem.addEventListener("playing", () => {
        console.log("Playing!")
        sendCommand(UNSUSPEND, videoElem.currentTime)
})

videoElem.addEventListener("canplay", () => {
        console.log("can play!")
        sendCommand(UNSUSPEND, videoElem.currentTime)
})
videoElem.addEventListener("canplaythrough", () => {
        console.log("can play!")
        sendCommand(UNSUSPEND, videoElem.currentTime)
})

fsButton.addEventListener("click", () => {
        console.log("Force suspend!")
        sendCommand(SUSPEND, videoElem.currentTime)
        suspend = true;
})

videoElem.addEventListener("timeupdate", () => {
        if (Math.abs(last_ts - videoElem.currentTime) > 2) {
                console.log(`Peremotka ${last_ts}, ${videoElem.currentTime}`)
        } else {
                sendCommand(PING, videoElem.currentTime)
        }

        last_ts = videoElem.currentTime;
})

videoElem.addEventListener("error", () => {
	// reloadVideo()
})

if (navigator.getAutoplayPolicy == !undefined && (navigator.getAutoplayPolicy(videoElem) === "allowed-muted" ||
                navigator.getAutoplayPolicy(videoElem) === "disallowed")) {
        const newElement = document.createElement("h1");
        newElement.textContent = "Влючи автоплей, ублюдок"
        document.getElementsByTagName("body")[0].insertAdjacentElement("beforebegin", newElement)
}

selectFileElem.addEventListener("change", selectFile)
