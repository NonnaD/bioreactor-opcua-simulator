# console.py: a web console for the bioreactor.
#
# It is one more OPC UA client (like api.py), with a small web server in front:
#   browser --HTTP POST /api/command--> console.py --Method call--> server.py
#   browser <--Server-Sent Events /events-- console.py <--subscription-- server.py
#
# Run it (with server.py already running):
#   uvicorn console:app --port 8000
# then open http://localhost:8000

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from asyncua import Client, ua
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

URL = os.environ.get("OPC_URL", "opc.tcp://localhost:4840/bioreactor/")

# Every value the page shows: "Object.Variable" -> browse path under Bioreactor
WATCH = {
    "State": ["2:State"],
    "Temperature.Value": ["2:Temperature", "2:Value"],
    "Temperature.Setpoint": ["2:Temperature", "2:Setpoint"],
    "Ph.Value": ["2:Ph", "2:Value"],
    "Ph.Setpoint": ["2:Ph", "2:Setpoint"],
    "DissolvedOxygen.Value": ["2:DissolvedOxygen", "2:Value"],
    "DissolvedOxygen.Setpoint": ["2:DissolvedOxygen", "2:Setpoint"],
    "Agitator.Speed": ["2:Agitator", "2:Speed"],
    "Agitator.Setpoint": ["2:Agitator", "2:Setpoint"],
    "BasePump.Output": ["2:BasePump", "2:Output"],
    "BasePump.Fault": ["2:BasePump", "2:Fault"],
    "Simulation.SpeedFactor": ["2:Simulation", "2:SpeedFactor"],
}

bioreactor = None   # the Bioreactor node, set when the console connects
names = {}          # node -> "Object.Variable"
latest = {}         # "Object.Variable" -> last known value (for new browser tabs)
browsers = []       # one queue per open browser tab


class ChangeHandler:
    def datachange_notification(self, node, val, data):
        name = names[node]
        latest[name] = val
        for queue in browsers:
            queue.put_nowait({"name": name, "value": val})


@asynccontextmanager
async def lifespan(app):
    """Connect to the OPC UA server when the web server starts; disconnect when it stops."""
    global bioreactor
    async with Client(URL) as client:
        bioreactor = await client.nodes.objects.get_child("2:Bioreactor")
        for name, path in WATCH.items():
            try:
                node = await bioreactor.get_child(path)
            except ua.UaStatusCodeError:                 # e.g. an older server.py without this node
                print(f"WARNING: {name} not found on the server, skipping it (restart server.py?)")
                continue
            names[node] = name
        subscription = await client.create_subscription(200, ChangeHandler())
        await subscription.subscribe_data_change(list(names))
        print("Console connected to", URL)
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def page():
    return FileResponse(Path(__file__).parent / "console.html")


@app.post("/api/command")
async def command(body: dict):
    """Body: {"command": "Agitator.SetSpeed", "value": 120} or {"command": "Start"}."""
    name = body.get("command", "")
    value = body.get("value")
    try:
        if "." in name:                                  # "Agitator.SetSpeed"
            obj_name, method = name.split(".", 1)
            obj = await bioreactor.get_child(f"2:{obj_name}")
        else:                                            # "Start"
            obj, method = bioreactor, name
        args = [] if value is None else [float(value)]   # float(): the int bug again
        await obj.call_method(f"2:{method}", *args)
        return {"ok": True}
    except (ua.UaStatusCodeError, ValueError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)


@app.get("/events")
async def events():
    """Server-Sent Events: the browser keeps this request open and gets each change."""
    queue = asyncio.Queue()
    browsers.append(queue)

    async def stream():
        try:
            for name, value in latest.items():           # first: the current values
                yield f"data: {json.dumps({'name': name, 'value': value})}\n\n"
            while True:                                  # then: every change
                change = await queue.get()
                yield f"data: {json.dumps(change)}\n\n"
        finally:
            browsers.remove(queue)                       # the tab was closed

    return StreamingResponse(stream(), media_type="text/event-stream")
