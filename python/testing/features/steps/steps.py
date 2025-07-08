from behave import given, when, then
import multiprocessing
import trafficlight
import time
from testing.simulate_hw import SimLight, SimController


def launch_trafficlight(name, with_comm=False, with_controller=False):
    hw = SimLight()
    if with_comm:
        pass

    return {
        "controller": None if not with_controller else SimController(),
        "hardware": hw,
        "comm": None,
    }


@given(
    "I have one traffic light called {name} which has no communication stack running"
)
def single_traffic_light(context, name):
    assert name not in context.traffic_lights
    context.traffic_lights[name] = launch_trafficlight(name, False, False)


@given("I have one traffic light called {name}")
def named_traffic_light(context, name):
    assert name not in context.traffic_lights
    context.traffic_lights[name] = launch_trafficlight(name, True, False)


@given("the {color} bulb of {name} is defective")
def bulb_defective(context, color, name):
    assert name in context.traffic_lights
    assert color in {"yellow", "red", "green"}

    context.traffic_lights[name]["hardware"].fail_bulb(color)


@when("I turn the traffic light {name} on")
def turn_light_on(context, name):
    assert name in context.traffic_lights
    context.traffic_lights[name]["hardware"].switch_on()
    # Start up hardware first, then br`ing up "pi" if any


@when("I turn the traffic light {name} on {duration} seconds later")
def turn_on_delayed(context, name, duration):
    assert name in context.traffic_lights
    time.sleep(int(duration))
    context.traffic_lights[name]["hardware"].switch_on()


@when("wait for {name} to settle")
def wait_settle(context, name):
    assert name in context.traffic_lights
    hw = context.traffic_lights[name]["hardware"]
    states = []
    count = 0
    while len(set(states)) != 1 or len(states) < 10:
        count += 1
        time.sleep(1)
        states.append((hw.red, hw.yellow, hw.green))
        if len(states) > 10:
            states.pop(0)
        assert count < 30
    return


@then("the {color} light of {name} must try to flash in {time} second rhythm")
def check_blink(context, color, name, time):
    pass


@then("the {color} light of {name} must be on permanently")
def check_on(context, color, name):
    # TODO: Check if permanent!!
    assert context.traffic_lights[name]["hardware"].is_on(color)
