import asyncio
from asyncua import Server, uamethod, ua
import sim

async def add_writable_var(parent_obj, name: str, val, idx):
        opc_var = await parent_obj.add_variable(idx, name, val)
        await opc_var.set_writable()
        return opc_var

async def send_to_sim(command, value=None):
    """The only seam to the simulator; in a distributed setup this becomes an HTTP call."""
    try:
        await sim.handle_command(command, value)
    except ValueError as error:
        print("Rejected:", error)
        # Return (don't raise) a status code: a raised error always becomes BadUnexpectedError
        return ua.StatusCode(ua.StatusCodes.BadOutOfRange)
    except RuntimeError as error:
        print("Device failure:", error)
        return ua.StatusCode(ua.StatusCodes.BadDeviceFailure)

@uamethod
async def start(parent):
    return await send_to_sim("Start")

@uamethod
async def stop(parent):
    return await send_to_sim("Stop")

@uamethod
async def set_temperature_setpoint(parent, value):
    return await send_to_sim("Temperature.SetSetpoint", value)

@uamethod
async def set_ph_setpoint(parent, value):
    return await send_to_sim("Ph.SetSetpoint", value)

@uamethod
async def set_do_setpoint(parent, value):
    return await send_to_sim("DissolvedOxygen.SetSetpoint", value)

@uamethod
async def set_agitator_speed(parent, value):
    return await send_to_sim("Agitator.SetSpeed", value)

@uamethod
async def set_base_pump_output(parent, value):
    return await send_to_sim("BasePump.SetOutput", value)

@uamethod
async def inject_pump_fault(parent):
    return await send_to_sim("BasePump.InjectFault")

@uamethod
async def clear_pump_fault(parent):
    return await send_to_sim("BasePump.ClearFault")

@uamethod
async def set_speed_factor(parent, value):
    return await send_to_sim("Simulation.SetSpeedFactor", value)


async def main():
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://localhost:4840/bioreactor/")


    idx = await server.register_namespace("urn:opc-practice:bioreactor")
    bioreactor = await server.nodes.objects.add_object(idx, "Bioreactor")
    state = await add_writable_var(bioreactor, "State", "Idle", idx)


    temperature = await bioreactor.add_object(idx, "Temperature")
    temp_val = await add_writable_var(temperature, "Value", 37.0, idx)
    temp_setpoint = await add_writable_var(temperature, "Setpoint", 37.0, idx)

    ph = await bioreactor.add_object(idx, "Ph")
    ph_val = await add_writable_var(ph, "Value", 7.0, idx)
    ph_setpoint = await add_writable_var(ph, "Setpoint", 7.0, idx)


    dissolved_oxygen = await bioreactor.add_object(idx, "DissolvedOxygen")
    do_val = await add_writable_var(dissolved_oxygen, "Value", 40.0, idx)
    do_setpoint = await add_writable_var(dissolved_oxygen, "Setpoint", 40.0, idx)

    agitator = await bioreactor.add_object(idx, "Agitator")
    ag_val = await add_writable_var(agitator, "Speed", 0.0, idx)
    ag_setpoint = await add_writable_var(agitator, "Setpoint", 0.0, idx)

    base_pump = await bioreactor.add_object(idx, "BasePump")
    base_pump_output = await add_writable_var(base_pump, "Output", 0.0, idx)
    base_pump_fault = await add_writable_var(base_pump, "Fault", False, idx)

    simulation = await bioreactor.add_object(idx, "Simulation")       # simulation only
    speed_factor = await add_writable_var(simulation, "SpeedFactor", 10.0, idx)

    await bioreactor.add_method(idx, "Start", start)
    await bioreactor.add_method(idx, "Stop", stop)
    await temperature.add_method(idx, "SetSetpoint", set_temperature_setpoint, [ua.VariantType.Double], [])
    await ph.add_method(idx, "SetSetpoint", set_ph_setpoint, [ua.VariantType.Double], [])
    await dissolved_oxygen.add_method(idx, "SetSetpoint", set_do_setpoint, [ua.VariantType.Double], [])
    await agitator.add_method(idx, "SetSpeed", set_agitator_speed, [ua.VariantType.Double], [])
    await base_pump.add_method(idx, "SetOutput", set_base_pump_output, [ua.VariantType.Double], [])
    await base_pump.add_method(idx, "InjectFault", inject_pump_fault)  # simulation only
    await base_pump.add_method(idx, "ClearFault", clear_pump_fault)    # simulation only
    await simulation.add_method(idx, "SetSpeedFactor", set_speed_factor, [ua.VariantType.Double], [])

    async with server:
        print("Server running")
        sim_task = asyncio.create_task(sim.run())  # start the simulator's clock
        while True:
            await asyncio.sleep(1)


asyncio.run(main())