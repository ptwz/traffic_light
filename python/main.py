import argparse
import os
import time
import logging
from trafficlight import TrafficLightGroup, TrafficLightController, MQTTItem

parser = argparse.ArgumentParser(description="Trafflic light controller")

parser.add_argument("host")
parser.add_argument("name")
parser.add_argument("remotename")
parser.add_argument("tty")
parser.add_argument("-l", "--log-level")
parser.add_argument("-u", "--username")
parser.add_argument("-p", "--port", default=1883, type=int)
parser.add_argument("-c", "--controller", action="store_true")
parser.add_argument("-C", "--controller-port", default="auto")

args = parser.parse_args()

logging.basicConfig(level=args.log_level)

if "MQTT_PASS" not in os.environ:
    print("Please set MQTT_PASS environment variable")

mqtt_param = {
    "host": args.host,
    "username": args.username,
    "password": os.environ["MQTT_PASS"],
    "port": args.port,
}

MQTTItem.mqtt_daemon(args.name, mqtt_param)

group = TrafficLightGroup(args.name, args.tty, args.remotename)
if args.controller:
    controller = TrafficLightController(args.name + "-controller", args.controller_port)
else:
    controller = None

while True:
    time.sleep(2)
    if controller and not controller.ok:
        controller.connect()
