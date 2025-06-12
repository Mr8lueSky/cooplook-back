let alertsElm = document.getElementById("alerts")


let clearAlerts = () => {
        alertsElm.innerHTML = ""
}


let showAlerts = async () => {
        console.log("Showing alerts!")
        alerts = await cookieStore.get("exc")
        if (!alerts) return
        try {
                console.log(alerts.value)
                alerts = JSON.parse(JSON.parse(alerts.value))
        } catch (e) {
                console.log(`Failed to parse alert: ${e}`)
                await cookieStore.delete('exc')
                return;
        }
        alerts.forEach(alertMsg => {
                let alertElm = document.createElement("h1")
                alertElm.textContent = alertMsg
                alertsElm.appendChild(alertElm)
        });
        await cookieStore.delete('exc')
}


document.onload = showAlerts()
