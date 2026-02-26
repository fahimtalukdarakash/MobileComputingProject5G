const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p); }
    catch (e) { return null; }
}
const data = msg.payload;
msg.topic = "Pressure (hPa)";
msg.payload = Number(data.pressure_hpa);
return msg;