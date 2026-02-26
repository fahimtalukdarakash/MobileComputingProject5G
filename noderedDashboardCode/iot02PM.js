const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p); }
    catch (e) { return null; }
}
const data = msg.payload;
msg.topic = "PM 2.5";
msg.payload = Number(data.pm2_5_ugm3);
return msg;