import asyncio
from asyncua import Client, ua

URL = "opc.tcp://localhost:4840/bioreactor/"


class ChangeHandler:
    def datachange_notification(self, node, val, data):
        print("  change:", names[node], "=", val)


names = {}  # node -> readable name, filled in main()


async def start(bioreactor):
    await bioreactor.call_method("2:Start")
    print("Start() -> Good")


async def stop(bioreactor):
    await bioreactor.call_method("2:Stop")
    print("Stop() -> Good")


async def set_agitator_speed(bioreactor, rpm):
    agitator = await bioreactor.get_child("2:Agitator")
    try:
        await agitator.call_method("2:SetSpeed", float(rpm))
        print(f"Agitator.SetSpeed({rpm}) -> Good")
    except ua.UaStatusCodeError as error:
        print(f"Agitator.SetSpeed({rpm}) -> {error}")


async def set_temperature_setpoint(bioreactor, celsius):
    temperature = await bioreactor.get_child("2:Temperature")
    await temperature.call_method("2:SetSetpoint", float(celsius))
    print(f"Temperature.SetSetpoint({celsius}) -> Good")


async def set_ph_setpoint(bioreactor, ph):
    ph_obj = await bioreactor.get_child("2:Ph")
    await ph_obj.call_method("2:SetSetpoint", float(ph))
    print(f"Ph.SetSetpoint({ph}) -> Good")


async def set_do_setpoint(bioreactor, percent):
    dissolved_oxygen = await bioreactor.get_child("2:DissolvedOxygen")
    await dissolved_oxygen.call_method("2:SetSetpoint", float(percent))
    print(f"DissolvedOxygen.SetSetpoint({percent}) -> Good")


async def set_base_pump_output(bioreactor, percent):
    base_pump = await bioreactor.get_child("2:BasePump")
    try:
        await base_pump.call_method("2:SetOutput", float(percent))
        print(f"BasePump.SetOutput({percent}) -> Good")
    except ua.UaStatusCodeError as error:
        print(f"BasePump.SetOutput({percent}) -> {error}")


# Test-only: in a real system, faults are injected through the simulator's own
# control interface, not through the API service.
async def inject_pump_fault(bioreactor):
    base_pump = await bioreactor.get_child("2:BasePump")
    await base_pump.call_method("2:InjectFault")
    print("BasePump.InjectFault() -> Good")


async def clear_pump_fault(bioreactor):
    base_pump = await bioreactor.get_child("2:BasePump")
    await base_pump.call_method("2:ClearFault")
    print("BasePump.ClearFault() -> Good")


async def main():
    async with Client(URL) as client:
        bioreactor = await client.nodes.objects.get_child("2:Bioreactor")

        watch = {
            "State": ["2:State"],
            "Ph.Value": ["2:Ph", "2:Value"],
            "Ph.Setpoint": ["2:Ph", "2:Setpoint"],
            "Agitator.Speed": ["2:Agitator", "2:Speed"],
            "BasePump.Output": ["2:BasePump", "2:Output"],
            "BasePump.Fault": ["2:BasePump", "2:Fault"],
        }
        for name, path in watch.items():
            node = await bioreactor.get_child(path)
            names[node] = name

        subscription = await client.create_subscription(500, ChangeHandler())
        await subscription.subscribe_data_change(list(names))
        await asyncio.sleep(1)  # let the first notification (current values) arrive

        # Scenario: ramp the agitator to 100 rpm and watch for 3 real seconds.
        # At SPEED = 1 you see 3 steps; at SPEED = 10 it reaches 100.
        print("--- scenario ---")
        await start(bioreactor)
        await set_agitator_speed(bioreactor, 100)
        await asyncio.sleep(3)

        await asyncio.sleep(1)  # stay alive so the pushed changes can arrive


asyncio.run(main())
