import argparse
import os
import time
import logging
from trafficlight import TrafficLightGroup

parser = argparse.ArgumentParser(description="Trafflic light controller")

parser.add_argument("name")
parser.add_argument("remotename")
parser.add_argument("tty")
parser.add_argument("-s", "--server")
parser.add_argument("-p", "--port")
parser.add_argument("-u", "--username")
parser.add_argument("-l", "--log-level")

args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG)

if "MQTT_PASS" not in os.environ:
    print("Please set MQTT_PASS environment variable")

mqtt_param = {
    "username": args.username,
    "password": os.environ["MQTT_PASS"],
    "host": args.server,
    "port": args.port,
}

group = TrafficLightGroup(args.name, args.tty, args.remotename, mqtt_param)

while True:
    time.sleep(0.1)
