const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p); }
    catch (e) { return null; }
}
const data = msg.payload;
msg.topic = "Temperature (°C)";
msg.payload = Number(data.temperature_c);
return msg;