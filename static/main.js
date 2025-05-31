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


videoElem.addEventListener("play", async (event) => {
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
        currentStatusElem.textContent = "PLAY"
        console.log("Play event")
})

videoElem.addEventListener("pause", async (event) => {
        if (ignorePause > 0) {
                ignorePause -= 1;
                console.log(`Skipping pause, left ${ignorePause}`)
                return;
        }
        sendCommand(PAUSE, videoElem.currentTime)
        currentStatusElem.textContent = "PAUSE"
        console.log("Pause event")
})

const PLAY = "pl"
const PAUSE = "pa"
const PING = "pi"
const SET_CT = "sc"
const PEOPLE_COUNT = "pc"
const SUSPEND = "sp"
const UNSUSPEND = "up"
const FORCE_UNSUSPEND = "fu"


async function wsOnMessage(message) {
        let [cmd, ts] = message.data.split(' ')
        ts = parseFloat(ts)
        console.log(`Command rc: ${cmd}, current time: ${ts}`)
        if (cmd == SET_CT) {
                videoElem.currentTime = ts;
                last_ts = ts;
        } else if (cmd == PLAY) {
                console.log("PLAY FROM SERVER")
                currentStatusElem.textContent = "PLAY";
                videoElem.currentTime = ts;
                await play_video()
        } else if (cmd == PAUSE) {
                currentStatusElem.textContent = "PAUSE";
                console.log("PAUSE FROM SERVER")
                videoElem.currentTime = ts;
                await pause_video()
        } else if (cmd == SUSPEND) {
                console.log("SUSPEND")
                currentStatusElem.textContent = "SUSPEND";
                await pause_video()
                suspend = true;
        } else if (cmd == UNSUSPEND) {
                console.log("UNSUSPEND")
                suspend = false;
        } else if (cmd == PEOPLE_COUNT) {
                peopleCountElem.textContent = ts;
        	return;
	}

        videoElem.currentTime = ts;
}



let ws = new WebSocket(`/rooms/${room_id}/ws`);
ws.onmessage = wsOnMessage;


let sendCommand = (cmd, data) => {
        console.log(`Sn: ${cmd} ${data}`)
        ws.send(`${cmd} ${data}`)
}


ws.onclose = async () => {
        console.log("Socket closed.")
        videoElem.remove();

}

videoElem.addEventListener("playing", (event) => {
        console.log("Playing!")
	sendCommand(UNSUSPEND, videoElem.currentTime)
})

videoElem.addEventListener("canplay", (event) => {
        console.log("can play!")
	sendCommand(UNSUSPEND, videoElem.currentTime)
})
videoElem.addEventListener("canplaythrough", (event) => {
console.log("can play!")
sendCommand(UNSUSPEND, videoElem.currentTime)
})

fsButton.addEventListener("click", (event) => {
        console.log("Force suspend!")
        sendCommand(SUSPEND, videoElem.currentTime)
        suspend = true;
})

videoElem.addEventListener("timeupdate", (event) => {
        if (Math.abs(last_ts - videoElem.currentTime) > 1) {
                console.log("Peremotka")
                sendCommand(SET_CT, videoElem.currentTime)
        } else {
                sendCommand(PING, videoElem.currentTime)
        }
        last_ts = videoElem.currentTime;
})

if (navigator.getAutoplayPolicy == !undefined && (navigator.getAutoplayPolicy(videoElem) === "allowed-muted" ||
                navigator.getAutoplayPolicy(videoElem) === "disallowed")) {
        const newElement = document.createElement("h1");
        newElement.textContent = "Влючи автоплей, ублюдок"
        document.getElementsByTagName("body")[0].insertAdjacentElement("beforebegin", newElement)
}
