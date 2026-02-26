const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p); }
    catch (e) { return null; }
}
const data = msg.payload;
msg.topic = "Battery (%)";
msg.payload = Number(data.battery_percent);
return msg;