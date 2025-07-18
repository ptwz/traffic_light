import time


def before_scenario(context, scenario):
    context.traffic_lights = {}


def after_scenario(context, scenario):
    for light in context.traffic_lights.values():
        light["hardware"].switch_off()
        light["hardware"].shutdown = True
        try:
            light["comm"].shutdown()
        except AttributeError:
            pass
        try:
            light["controller_comm"].shutdown()
        except AttributeError:
            pass
    try:
        context.mqtt["daemon"].terminate()
        time.sleep(5)
        del context.mqtt
    except AttributeError:
        pass
