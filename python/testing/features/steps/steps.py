from behave import given, when, then
import multiprocessing
import trafficlight
import subprocess
import time
import string
import random
import os
from queue import Queue, Empty
import logging
import testing.mosquitto_dynsec as dynsec
import threading
import sys
import requests
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
        "controller_comm": None,
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


@given("I have a webserver")
def have_webserver(context):
    port = 5000
    env = {
        "MQTT_HOST": "127.0.0.1",
        "MQTT_PORT": str(context.mqtt["port"]),
        "MQTT_USER": "admin",
        "MQTT_PASS": context.mqtt["adminpassword"],
    }
    webserver = {
        "port": port,
        "process": subprocess.Popen(
            ["flask", "--app", "webserver", "run", "--port", str(port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
    }
    context.webserver = webserver


@given("I have an mqtt server")
def have_mqtt_server(context):
    have_mqtt_server_delayed(context, 0)


@given("I have an mqtt server coming up delayed by {delay} seconds")
def have_mqtt_server_delayed(context, delay):
    context.mqtt = {
        "server_task": None,
        "port": 1883,
        "username": "ampel",
        "password": "".join(random.choice(string.ascii_lowercase) for i in range(16)),
        "adminpassword": "".join(
            random.choice(string.ascii_lowercase) for i in range(16)
        ),
        "passwdfile": "/tmp/mosquitto.passwd",
    }

    with open("/tmp/mosquitto.conf", "w") as f:
        # f.write(f"password_file {context.mqtt['passwdfile']}\n")
        f.write(f"listener {context.mqtt['port']}\n")
        f.write("plugin /usr/lib/x86_64-linux-gnu/mosquitto_dynamic_security.so\n")
        f.write("plugin_opt_config_file /tmp/dynamic_security.json\n")

    try:
        os.unlink("/tmp/dynamic_security.json")
    except FileNotFoundError:
        pass
    # Now generate dynamic_security.json
    subprocess.run(
        [
            "mosquitto_ctrl",
            "dynsec",
            "init",
            "/tmp/dynamic_security.json",
            "admin",
            context.mqtt["adminpassword"],
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ready = threading.Event()
    context.mqtt_auth_queue = Queue()

    def delayed_start():
        logging.debug("Starting MQTT broker")
        time.sleep(int(delay))

        def daemon_watcher():
            for line in daemon.stderr:
                logging.debug("mosquitto - %s", line)
                if b"running" in line:
                    ready.set()

        daemon = subprocess.Popen(
            ["mosquitto", "-c", "/tmp/mosquitto.conf"],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        threading.Thread(target=daemon_watcher, daemon=True).start()
        ready.wait()

        context.mqtt["daemon"] = daemon
        # Wait for daemon to report ready for duty
        logging.debug("mosquitto broker daemon started")
        # print("MQTT quit: ", context.mqtt["daemon"].wait())
        # Give server some time to start up

        # Set up roles for failed and working MQTT
        dynsec.add_role(
            "admin",
            context.mqtt["adminpassword"],
            role_name="mqtt_ok",
        )
        for acltype in {
            "subscribePattern",
            "publishClientReceive",
            "publishClientSend",
        }:
            dynsec.add_role_acl(
                "admin",
                context.mqtt["adminpassword"],
                role_name="mqtt_ok",
                acltype=acltype,
                pattern="ampel/#",
                mode="allow",
            )

        dynsec.add_role(
            "admin",
            context.mqtt["adminpassword"],
            role_name="mqtt_fail",
        )
        for acltype in {
            "subscribePattern",
            "publishClientReceive",
            "publishClientSend",
        }:
            dynsec.add_role_acl(
                "admin",
                context.mqtt["adminpassword"],
                role_name="mqtt_fail",
                acltype=acltype,
                pattern="ampel/#",
                mode="deny",
            )
        while True:
            try:
                (command, arguments) = context.mqtt_auth_queue.get(timeout=0.2)
                logging.debug("Loading ACL: %s", arguments)
                command(*arguments)
            except Empty:
                continue

    # Now start mosquitto process
    context.mqtt_thread = threading.Thread(target=delayed_start, daemon=True)
    context.mqtt_thread.start()
    if not delay:
        ready.wait()
    mqtt_data = {
        "host": "127.0.0.1",
        "port": context.mqtt["port"],
        "username": context.mqtt["username"],
        "password": context.mqtt["password"],
    }
    trafficlight.MQTTItem.mqtt_daemon("testing", mqtt_data)


@given("the PIC of {name} generates {seconds} seconds of garbled data")
def garbled(context, name, seconds):
    assert name in context.traffic_lights
    seconds = int(seconds)
    assert seconds > 0


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
        env = os.environ.copy()
        mqtt_data = {
            "host": "127.0.0.1",
            "port": context.mqtt["port"],
            "username": name,
            "password": "".join(
                random.choice(string.ascii_lowercase) for i in range(16)
            ),
        }
        try:
            context.mqtt_auth_queue.put((
                dynsec.add_client,
                (
                    "admin",
                    context.mqtt["adminpassword"],
                    mqtt_data["username"],
                    mqtt_data["password"],
                ),
            ))
            # By default, allow MQTT communication
            context.mqtt_auth_queue.put((
                dynsec.add_client_role,
                ("admin", context.mqtt["adminpassword"], name, "mqtt_ok"),
            ))
        except AttributeError:
            # Will most likely be raised by accessing mqtt_auth_queue w/o ruinning mqtt
            pass

        env["MQTT_PASS"] = mqtt_data["password"]

        # Get name of the other light, too
        other_name = list(set(context.traffic_lights.keys()) - set([name])).pop()
        args = [
            "python3",
            "main.py",
            mqtt_data["host"],
            name,
            other_name,
            light["hardware"].pts,
            "-p",
            str(mqtt_data["port"]),
            "-u",
            mqtt_data["username"],
        ]
        if light["controller"]:
            args += ["-c", "-C", light["controller"].pts]
        light["comm"] = subprocess.Popen(
            args,
            env=env,
        )

    light["hardware"].switch_on()
    # Start up hardware first, then bring up "pi" if any


@when("I press the {color} button on the controller of {name}")
def controller_press(context, color, name):
    assert color in ("red", "green")
    assert name in context.traffic_lights
    light = context.traffic_lights[name]
    assert light["controller"]
    controller = light["controller"]
    if color == "green":
        controller.press_green()
    elif color == "red":
        controller.press_red()


@when("I turn the traffic light {name} on {duration} seconds later")
def turn_on_delayed(context, name, duration):
    assert name in context.traffic_lights
    time.sleep(int(duration))
    turn_light_on(context, name)


@when("I wait for {name} to settle")
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


@then("the webserver indicates that {name} is alive")
@then("webserver indicates that {name} is alive")
def check_webserver_alive(context, name, alive=True):
    answer = requests.get(
        f"http://localhost:{context.webserver['port']}/api/v1/states",
    )
    result = answer.json()
    assert result[f"ampel/{name}/state"]["alive"] == alive, (
        f"The webserver reported {name} to be {alive}, report was {result}"
    )


@then("the webserver indicates that {name} is not alive")
@then("webserver indicates that {name} is not alive")
def check_webserver_not_alive(context, name):
    check_webserver_alive(context, name, alive=False)


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
        assert count < 30, (
            "States not converging " + str(states) + " " + hw.traffic_state
        )


@when("the communication of {name} is interrupted for {duration} seconds")
def comm_interrupted(context, name, duration):
    assert name in context.traffic_lights
    context.mqtt_auth_queue.put((
        dynsec.remove_client_role,
        ("admin", context.mqtt["adminpassword"], name, "mqtt_ok"),
    ))
    context.mqtt_auth_queue.put((
        dynsec.add_client_role,
        ("admin", context.mqtt["adminpassword"], name, "mqtt_fail"),
    ))
    time.sleep(int(duration))


@when("the communication of {name} is restored")
def comm_fixed(context, name):
    assert name in context.traffic_lights
    context.mqtt_auth_queue.put((
        dynsec.remove_client_role,
        ("admin", context.mqtt["adminpassword"], name, "mqtt_fail"),
    ))
    context.mqtt_auth_queue.put((
        dynsec.add_client_role,
        ("admin", context.mqtt["adminpassword"], name, "mqtt_ok"),
    ))


@then("the {color} light of both lights must be on permanently")
def check_all_on(context, color):
    for name, light in context.traffic_lights.items():
        hw = light["hardware"]
        assert hw.is_on(color), (
            f"{name} should be permanently {color}. State {hw.get_color_states()}"
        )


@then("the {color} light of {name} must be on permanently")
def check_on(context, color, name):
    # TODO: Check if permanent!!
    light = context.traffic_lights[name]
    assert light["hardware"].is_on(color), (
        str(light["comm"]) + " Should be permanently " + color
    )
