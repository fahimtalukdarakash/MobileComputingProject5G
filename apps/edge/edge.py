from flask import Flask, request, jsonify
import os, time, json

app = Flask(__name__)

@app.get("/")
def ok():
    return "edge ok\n"

@app.post("/telemetry")
def telemetry():
    data = request.get_json(silent=True) or {}
    print(f"[{time.strftime('%H:%M:%S')}] telemetry: {json.dumps(data)}", flush=True)
    return jsonify({"status":"ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
