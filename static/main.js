let videoElem = document.getElementById("video");


videoElem.addEventListener("play", (event) => {
    ws.send(`${PLAY} ${videoElem.currentTime}`)
    console.log("Play event")
})

videoElem.addEventListener("pause", (event) => {
    ws.send(`${PAUSE} ${videoElem.currentTime}`)
    console.log("Pause event")
})


const PLAY = "pl"
const PAUSE = "pa"
const PING = "pi"
const SET_CT = "sc"
const PEOPLE_COUNT = "pc"
let initial = true;
let last_ts = 0;

async function wsOnMessage(message) {
    let [cmd, ts] = message.data.split(' ')
    ts = parseFloat(ts)
    console.log(`Command rc: ${cmd}, current time: ${ts}`)
    if (cmd == SET_CT) {
        videoElem.currentTime = ts;
        last_ts = ts;
    } else if (cmd == PLAY) {
        videoElem.currentTime = ts;
        videoElem.play()
    } else if (cmd == PAUSE) {
        videoElem.currentTime = ts;
        videoElem.pause()
    }

    if (initial) {
        message.target.send(`${PAUSE} ${ts}`);
        videoElem.pause();
        initial = false;
    }
}



let ws = new WebSocket(`/rooms/${room_id}/ws`);

ws.onmessage = wsOnMessage;


videoElem.addEventListener("waiting", (event) => {
    console.log("Waiting!")
//    ws.send(`${PAUSE} ${videoElem.currentTime}`)
})

videoElem.addEventListener("playing", (event) => {
    console.log("Playing!")
//    ws.send(`${PLAY} ${videoElem.currentTime}`)
})

videoElem.addEventListener("seeking", (event) => {
    console.log("Seeking!")
})

videoElem.addEventListener("seeked", (event) => {
    console.log("seeked!")
})

videoElem.addEventListener("stalled", (event) => {
    console.log("Seeking!")
})

videoElem.addEventListener("timeupdate", (event) => {
    ws.send(`${PING} ${videoElem.currentTime}`)
    if (Math.abs(last_ts - videoElem.currentTime) > 1) {
        console.log("Peremotka")
        ws.send(`${SET_CT} ${videoElem.currentTime}`)
    }
    last_ts = videoElem.currentTime;
})

//if (navigator.getAutoplayPolicy(video) === "allowed") {
//  // The video element will autoplay with audio.
//} else if (navigator.getAutoplayPolicy(video) === "allowed-muted") {
//  // Mute audio on video
//  video.muted = true;
//} else if (navigator.getAutoplayPolicy(video) === "disallowed") {
//  // Set a default placeholder image.
//  video.poster = "http://example.com/poster_image_url";
//}
