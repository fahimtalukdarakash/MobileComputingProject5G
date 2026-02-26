const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p);}
    catch(e) {return null;}
}
const data = msg.payload;
msg.topic = "Humidity (%)";
msg.payload = Number(data.humidity_percent);
return msg;