const p = msg.payload;
if (typeof p === "string") {
    try { msg.payload = JSON.parse(p); }
    catch (e) { return null; } // drop bad messages
}
const data = msg.payload;
let prev_value;
if (data.ue === "ue-veh-02") {
    msg.topic = "Alert";
    msg.payload = data.alert;
    prev_value = msg.payload;
}
else{
    msg.topic = "Alert";
    msg.payload = prev_value;
}
return msg;