const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p);}
    catch(e) {return null;}
}
const data = msg.payload;
msg.topic = "CO2 (ppm)";
msg.payload = Number(data.co2_ppm);
return msg;