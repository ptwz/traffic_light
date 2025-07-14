from behave import given, when, then
import multiprocessing
import trafficlight
import subprocess
import time
import string
import random
from testing.simulate_hw import SimLight, SimController


def launch_trafficlight(context, name, with_comm=False, with_controller=False):
    hw = SimLight()
    if with_comm:
        comm = True
    else:
        comm = None
    return {
        "controller": SimController() if with_controller else None,
        "hardware": hw,
        "comm": comm,
    }


@given(
    "I have one traffic light called {name} which has no communication stack running"
)
def single_traffic_light(context, name):
    assert name not in context.traffic_lights
    context.traffic_lights[name] = launch_trafficlight(context, name, False, False)


@given("I have one traffic light called {name} with a controller")
def single_traffic_light(context, name):
    assert name not in context.traffic_lights
    context.traffic_lights[name] = launch_trafficlight(context, name, True, True)


@given("I have one traffic light called {name}")
def named_traffic_light(context, name):
    assert name not in context.traffic_lights
    context.traffic_lights[name] = launch_trafficlight(context, name, True, False)


@given("I have an mqtt server")
def have_mqtt_server(context):
    context.mqtt = {
        "server_task": None,
        "port": 1883,
        "username": "ampel",
        "password": "".join(random.choice(string.ascii_lowercase) for i in range(16)),
        "passwdfile": "/tmp/mosquitto.passwd",
    }
    with open("/tmp/mosquitto.conf", "w") as f:
        f.write(f"password_file {context.mqtt['passwdfile']}\n")
        f.write(f"listener {context.mqtt['port']}\n")

    # Now (re)generate mosquitto.passwd
    subprocess.run([
        "mosquitto_passwd",
        "-c",
        "-b",
        context.mqtt["passwdfile"],
        context.mqtt["username"],
        context.mqtt["password"],
    ])

    # Now start mosquitto process
    import sys

    context.mqtt["daemon"] = subprocess.Popen(
        ["mosquitto", "-c", "/tmp/mosquitto.conf"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # stderr=sys.stdout,
    )
    # Give server some time to start up
    time.sleep(1)


@given("the {color} bulb of {name} is defective")
def bulb_defective(context, color, name):
    assert name in context.traffic_lights
    assert color in {"yellow", "red", "green"}

    context.traffic_lights[name]["hardware"].fail_bulb(color)


@when("I turn the traffic light {name} on")
def turn_light_on(context, name):
    assert name in context.traffic_lights
    light = context.traffic_lights[name]
    if light["comm"] == True:
        mqtt_data = {
            "host": "127.0.0.1",
            "port": context.mqtt["port"],
            "username": context.mqtt["username"],
            "password": context.mqtt["password"],
        }
        # Get name of the other light, too
        other_name = list(set(context.traffic_lights.keys()) - set(name)).pop()

        light["comm"] = trafficlight.TrafficLightGroup(
            name, light["hardware"].pts, other_name, mqtt_data
        )
    light["hardware"].switch_on()
    # Start up hardware first, then br`ing up "pi" if any


@when("I turn the traffic light {name} on {duration} seconds later")
def turn_on_delayed(context, name, duration):
    assert name in context.traffic_lights
    time.sleep(int(duration))
    turn_light_on(context, name)


@when("wait for {name} to settle")
def wait_settle(context, name):
    assert name in context.traffic_lights
    hw = context.traffic_lights[name]["hardware"]
    # Force invalid states, in order to wait for proper settling
    states = [1, 2, 3]
    count = 0
    while (len(set(states)) != 1) and (set(states) != set([(0, 0, 0), (0, 1, 0)])):
        count += 1
        time.sleep(1)
        states.append((hw.red, hw.yellow, hw.green))
        if len(states) > 10:
            states.pop(0)
        assert count < 30
    return


@then("the {color} light of {name} must try to flash in {duration} second rhythm")
def check_blink(context, color, name, duration):
    assert name in context.traffic_lights
    hw = context.traffic_lights[name]["hardware"]
    states = []
    count = 0
    # Wait for two states to settle withing ten seconds
    while True:
        if set(states) == set([(0, 0, 0), (0, 1, 0)]):
            # Alternating yellow/black
            # TODO Have to check interval
            return
        count += 1
        time.sleep(1)
        states.append((hw.red, hw.yellow, hw.green))
        if len(states) > 10:
            states.pop(0)
        assert count < 30


@then("the {color} light of {name} must be on permanently")
def check_on(context, color, name):
    # TODO: Check if permanent!!
    light = context.traffic_lights[name]
    assert light["hardware"].is_on(color), (
        str(light["comm"]) + " Should be permanently green"
    )
