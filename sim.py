import asyncio
from asyncua import Client

state = {
    "State": "Idle",
    "Ph": {"Value": 7.0, "Setpoint": 7.0},
    "Temperature": {"Value": 37.0, "Setpoint": 37.0},
    "DissolvedOxygen": {"Value": 40.0, "Setpoint": 40.0},
    "Agitator": {"Speed": 0.0, "Setpoint": 0.0},
    "BasePump": {"Output": 0.0, "Fault": False},
    "Simulation": {"SpeedFactor": 10.0},   # time dilation: 1.0 = real time, 10.0 = ten times faster
}

RAMPS = [
    ("Temperature", "Value", 0.1),       # °C per second
    ("Ph", "Value", 0.05),               # pH per second
    ("DissolvedOxygen", "Value", 2.0),   # % per second
    ("Agitator", "Speed", 10.0),         # rpm per second
]

LIMITS = {
    "Temperature": (20.0, 45.0),       # °C
    "Ph": (6.0, 8.0),
    "DissolvedOxygen": (0.0, 100.0),   # % saturation
    "Agitator": (0.0, 500.0),          # rpm
    "BasePump": (0.0, 100.0),          # %
    "Simulation": (0.5, 100.0),        # speed factor
}

URL = "opc.tcp://localhost:4840/bioreactor/"

async def push_state():
    async with Client(URL) as client:
        bioreactor = await client.nodes.objects.get_child("2:Bioreactor")

        for key in state:
            value = state[key]
            if isinstance(value, dict):
                for name, number in value.items():
                   opc_obj = await bioreactor.get_child([f"2:{key}", f"2:{name}"])
                   await opc_obj.write_value(number)
            else:
                s = await bioreactor.get_child([f"2:{key}"])
                await s.write_value(value)



def print_state():
    for key in state:
        value = state[key]
        if isinstance(value, dict):
            for name, number in value.items():
                print(key, name, number)
        else:
            print(key, value)

def step_toward(current, target, step):
    """Move current one step toward target, without overshooting."""
    if current < target:
        return round(min(current + step, target), 3)  # going up
    else:
        return round(max(current - step, target), 3)  # going down (or already there)

async def handle_command(command: str, value=None):
    if value is not None:                      # e.g. "Agitator.SetSpeed", 30.0
        obj = command.split(".")[0]            # -> "Agitator"
        low, high = LIMITS[obj]
        if not low <= value <= high:
            raise ValueError(f"{command}({value}) is outside {low}..{high}")

    if command == "Stop":
        state["State"] = "Idle"
    elif command == "Start":
        state["State"] = "Running"
    elif command == "Agitator.SetSpeed":
        state["Agitator"]["Setpoint"] = value
    elif command == "Temperature.SetSetpoint":
        state["Temperature"]["Setpoint"] = value
    elif command == "Ph.SetSetpoint":
        state["Ph"]["Setpoint"] = value
    elif command == "DissolvedOxygen.SetSetpoint":
        state["DissolvedOxygen"]["Setpoint"] = value
    elif command == "BasePump.SetOutput":
        if state["BasePump"]["Fault"]:
            raise RuntimeError("BasePump is broken")
        state["BasePump"]["Output"] = value
    elif command == "BasePump.InjectFault":      # break it
        state["BasePump"]["Fault"] = True
        state["BasePump"]["Output"] = 0.0         # a broken pump stops
    elif command == "BasePump.ClearFault":       # repair it
        state["BasePump"]["Fault"] = False
    elif command == "Simulation.SetSpeedFactor": # simulation only: time dilation
        state["Simulation"]["SpeedFactor"] = value
    else:
        print(f"Unknown Command: {command}")
        return  # nothing changed -> nothing to push

    await push_state()  # the simulator publishes its own state


async def run():
    """The simulator's clock: every simulated second, move each value one step toward its setpoint."""
    while True:
        await asyncio.sleep(1 / state["Simulation"]["SpeedFactor"])   # one simulated second
        changed = False
        for obj, var, step in RAMPS:
            current = state[obj][var]
            target = state[obj]["Setpoint"]
            if current != target:
                state[obj][var] = step_toward(current, target, step)
                changed = True
        if changed:
            await push_state()          # only talk to the server if something moved



async def main():
    await handle_command("Start")
    await handle_command("Agitator.SetSpeed", 200.0)
    await run()

if __name__ == "__main__":
    asyncio.run(main())