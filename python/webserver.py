import json
import logging
import re
from flask import Flask, request, jsonify, send_from_directory
from os import environ
import paho.mqtt.client as mqtt


logger = logging.getLogger("MQTT")

states = {}
mqtt_conn = None


def handle_state(client, user_data, message):
    m = re.search(r"ampel/(.[a-zA-Z0-9/]+)/state", message.topic)
    if m:
        name = m.group(0)
        try:
            states[name] = json.loads(message.payload)
        except json.JSONDeocdeError:
            logger.error("Could not decode %s for %s", message.payload, name)


def on_connected():
    logger.debug("Adding subscritions")
    mqtt_conn.subscribe("ampel/+/state")
    mqtt_conn.message_callback_add("ampel/+/state", handle_state)


def connect_mqtt():
    mqtt_conn = mqtt.Client()
    mqtt_conn.username_pw_set(
        username=environ["MQTT_USER"], password=environ["MQTT_PASS"]
    )

    mqtt_conn.on_connect = on_connected
    mqtt_conn.connect(environ["MQTT_HOST"], int(environ["MQTT_PORT"]))
    return mqtt_conn


mqtt_conn = connect_mqtt()
app = Flask(__name__, static_folder="../website")


@app.route("/api/v1/states", methods=["GET"])
def get_state():
    return jsonify(states), 200


@app.route("/api/v1/command", methods=["POST"])
def send_command():
    if not request.json or request.json not in [True, False]:
        return jsonify({"message": "bad request"}), 400

    give_way = request.json

    payload = json.dumps({"give_way": bool(give_way)})
    mqtt_conn.publish("ampel/command", payload, retain=True)
    logger.debug("Published command!")
    return jsonify({"message": "ok"}), 200


@app.route("/", defaults=dict(filename=None))
@app.route("/<path:filename>", methods=["GET"])
def index(filename):
    filename = filename or "index.html"
    return send_from_directory("../website", filename)
