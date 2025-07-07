from behave import given, when, then, setup
import multiprocessing
import trafficlight
from testing.simulate_hw import SimLight, SimController


def before_all(context):
    context.traffic_lights = {}


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
    'I have one traffic light called "{name}" which has no communication stack running'
)
def single_traffic_light(context, name):
    assert name not in context.traffic_lights
    context.traffic_lights[name] = launch_trafficlight(name, False, False)


@given('the {color} light bulb of "{name}" is defective')
def bulb_defective(context, color, name):
    assert name in context.traffic_lights
    assert color in {"yellow", "red", "green"}

    context.traffic_lights[name]["hardware"].fail_bulb(color)


@when('I turn the traffic light "{name}" on')
def turn_light_on(context, name):
    assert name in context.traffic_lights
    # Start up hardware first, then bring up "pi" if any


@when('I turn the traffic light "{name}" on {time} seconds later')
def turn_on_delayed(context, name, time):
    assert name in context.traffic_lights
    time.sleep(time)


@when('wait for "{name}" to settle')
def wait_settle(context, name):
    assert name in context.traffic_lights


@then('Then the {color} light of "{name}" must try to flash in {time} second rhythm')
def check_blink(context, color, name, time):
    pass


@then('And the {color} light of "{name}" must be on permanently')
def check_on(context, color, name):
    pass
