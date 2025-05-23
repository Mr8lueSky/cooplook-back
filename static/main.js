let suspend = false;
let initial = true;
let last_ts = 0;

let videoElem = document.getElementById("video");
let fuButton = document.getElementById("force-uns")
let fsButton = document.getElementById("force-sus")

let peopleCountElem = document.getElementById("people-count");
let currentStatusElem = document.getElementById("current-status");


async function play_video() {
  let promise = videoElem.play();
  if (promise == undefined) return;
  promise.then(() => {
        
  }).catch(async (error) => {
      console.log(`Play video error ${error}`)
    })
}

async function pause_video() {
  let promise = videoElem.pause();

if (promise == undefined) return;
  promise.then(() => {
        
  }).catch(error => {
    console.log(`Failed to pause video ${error}`)
    })
}


videoElem.addEventListener("play", async (event) => {
  if (suspend) {
    await pause_video()
        return;
    }
    ws.send(`${PLAY} ${videoElem.currentTime}`)
    currentStatusElem.textContent = "PLAY"   
  console.log("Play event")
})

videoElem.addEventListener("pause", async (event) => {
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
    } else if (cmd == SUSPEND) {
currentStatusElem.textContent = "SUSPEND";
        videoElem.currentTime = ts;
        await pause_video()
        suspend = true;
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



//videoElem.addEventListener("waiting", (event) => {
//    console.log("Waiting!")
//    ws.send(`${SUSPEND} ${videoElem.currentTime}`)
//})

videoElem.addEventListener("playing", (event) => {
    console.log("Playing!")
    if (suspend) {
        ws.send(`${UNSUSPEND} ${videoElem.currentTime}`)
        suspend = false;
    }
})

videoElem.addEventListener("seeking", (event) => {
    console.log("Seeking!")
})

videoElem.addEventListener("seeked", (event) => {
    console.log("seeked!")
})

videoElem.addEventListener("stalled", (event) => {
    console.log("Stalled!")
})

videoElem.addEventListener("error", (event) => {
    console.log(`Error occured! ${event}`)
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

if (navigator.getAutoplayPolicy(videoElem) === "allowed-muted" || navigator.getAutoplayPolicy(videoElem) === "disallowed") {
    const newElement = document.createElement("h1");
    newElement.textContent = "Влючи автоплей, ублюдок"
    document.getElementsByTagName("body")[0].insertAdjacentElement("beforebegin", newElement)
}
