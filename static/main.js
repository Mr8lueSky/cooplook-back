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
  // if (suspend) {
  //   await pause_video()
  //   return;
  // }
  if (ignorePlay > 0) {
    ignorePlay -= 1;
    console.log(`Skipping play, left ${ignorePlay}`)
    return;
  }
  ws.send(`${PLAY} ${videoElem.currentTime}`)
  currentStatusElem.textContent = "PLAY"
  console.log("Play event")
})

videoElem.addEventListener("pause", async (event) => {
  if (ignorePause > 0) {
    ignorePause -= 1;
    console.log(`Skipping pause, left ${ignorePause}`)
    return;
  }
  ws.send(`${PAUSE} ${videoElem.currentTime}`)
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
    currentStatusElem.textContent = "PLAY";
    videoElem.currentTime = ts;
    await play_video()
  } else if (cmd == PAUSE) {
    currentStatusElem.textContent = "PAUSE";
    videoElem.currentTime = ts;
    await pause_video()
  // } else if (cmd == SUSPEND) {
  //   currentStatusElem.textContent = "SUSPEND";
  //   videoElem.currentTime = ts;
  //   await pause_video()
    //        suspend = true;
  } else if (cmd == PEOPLE_COUNT) {
    peopleCountElem.textContent = ts;
  }

  if (initial) {
    message.target.send(`${PAUSE} ${ts}`);
    await pause_video();
    initial = false;
  }
}



let ws = new WebSocket(`/rooms/${room_id}/ws`);
ws.onmessage = wsOnMessage;



ws.onclose = async () => {
  console.log("Socket closed.")
  videoElem.remove();

}

videoElem.addEventListener("playing", (event) => {
  console.log("Playing!")
  if (suspend) {
    ws.send(`${UNSUSPEND} ${videoElem.currentTime}`)
    suspend = false;
  }
})

videoElem.addEventListener("canplaythrough", (event) => {
  console.log("can play through!")
  ws.send(`${UNSUSPEND} ${videoElem.currentTime}`)
})


fuButton.addEventListener("click", (event) => {
  console.log("Force unsuspend!")
  ws.send(`${FORCE_UNSUSPEND} ${videoElem.currentTime}`)
})

fsButton.addEventListener("click", (event) => {
  console.log("Force suspend!")
  ws.send(`${SUSPEND} ${videoElem.currentTime}`)
})

videoElem.addEventListener("timeupdate", (event) => {
  ws.send(`${PING} ${videoElem.currentTime}`)
  if (Math.abs(last_ts - videoElem.currentTime) > 1) {
    console.log("Peremotka")
    ws.send(`${SET_CT} ${videoElem.currentTime}`)
  }
  last_ts = videoElem.currentTime;
})

if (navigator.getAutoplayPolicy == !undefined && (navigator.getAutoplayPolicy(videoElem) === "allowed-muted" ||
  navigator.getAutoplayPolicy(videoElem) === "disallowed")) {
  const newElement = document.createElement("h1");
  newElement.textContent = "Влючи автоплей, ублюдок"
  document.getElementsByTagName("body")[0].insertAdjacentElement("beforebegin", newElement)
}
