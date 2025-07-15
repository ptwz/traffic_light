import json
import logging
import os
import re
import random
import time
import serial
import threading
import paho.mqtt.client as mqtt


class MQTTItem:
    def __init__(self, name, mqtt_param):
        self.mqtt_param = mqtt_param
        self.name = name
        self._connect_mqtt()

    def _connect_mqtt(self):
        mqtt_param = self.mqtt_param
        if mqtt_param:
            # For clients with temporary name (listeners)
            if "name" in mqtt_param:
                name = mqtt_param["name"]
            else:
                name = self.name
            self.mqtt = mqtt.Client(client_id=name)
            self.mqtt.username_pw_set(
                username=mqtt_param["username"], password=mqtt_param["password"]
            )
            # self.mqtt.on_message = self._process_mqtt
            self.mqtt.on_connect = self._mqtt_connected
            self.mqtt.on_disconnect = self._mqtt_disconnected
            self.mqtt.on_connect_fail = self._mqtt_fail
            self.mqtt.connect(mqtt_param["host"], mqtt_param["port"])
            # TODO Enable TLS if necessary!!!
            self.state_topic = f"ampel/{self.name}/state"
            self.command_topic = "ampel/command"
            self.mqtt.loop_start()
            self.mqtt.will_set(
                self.state_topic,
                payload=json.dumps({"alive": False}),
                qos=2,
                retain=True,
            )

        else:
            self.mqtt = None

    def _mqtt_connected(
        self, client, userdata, connect_flags, reason_code, properties=None
    ):
        self.logger.info(self.name + " MQTT Connected")
        self._do_subscriptions()

    def _do_subscriptions(self):
        self.mqtt.subscribe(self.command_topic)

    def _mqtt_disconnected(self, client, userdata, rc, x=None, y=None, z=None):
        self.logger.info(" MQTT disconnect: %s", rc)

    def _mqtt_fail(self, client, userdata):
        self.logger.warning("mqtt_fail: %s %s", client, userdata)

    def mqtt_disconnect(self):
        try:
            self.mqtt.disconnect()
            self.mqtt.loop_stop()
            del self.mqtt
        except AttributeError:
            # Disregard if there is no mqtt in the first place
            pass


class TrafficLight(MQTTItem):
    """
    Base class for traffic light implementation.
    This provides a skeleton for creating either physical
    interfaces or virtual traffic lights.
    """

    def __init__(self, name, mqtt_param):
        self.logger = logging.getLogger(name)
        MQTTItem.__init__(self, name, mqtt_param)
        self.state = 99
        self.batt_voltage = 0
        self.lamp_currents = [0] * 3
        self.last_seen = 0
        self.maxage = 4
        self.give_way = True
        self.temp_error = False
        self.mqtt.message_callback_add(self.command_topic, self._process_mqtt_command)

    def __set__(self):
        return f"TrafficLight(name={self.name}, self.lamp_currents)"

    def _process_mqtt_command(self, client, user_data, message):
        self.logger.debug("TrafficLight got ", message)
        try:
            cmd = json.loads(message.topic)
        except json.JSONDecodeError:
            self.logger.warning("Could not parse command JSON: %s", message.topic)
            return
        self.set_green(cmd["give_Way"])

    def publish(self):
        self.logger.info(self.state)
        try:
            self.mqtt.publish(self.state_topic, self.to_json())
        except AttributeError as e:
            print(e)
            """ If there is no MQTT connection, disregard """
            pass

    def set_logger(self, logger):
        self.logger = logger

    def seen(self):
        """
        Test if the backend device has reported back
        in the last time within the self.maxage time frame
        """
        return (time.time() - self.last_seen) < self.maxage

    def send_update():
        pass

    def to_json(self):
        """
        Returns the state of a traffic light in JSON
        format.
        If challenge is passed, the data packet it will be
        encapsulated in a TransportWrapper.
        """
        data = {
            "state": self.state,
            "batt_voltage": self.batt_voltage,
            "lamp_currents": self.lamp_currents,
            "good": self.is_good(),
            "give_way": self.give_way,
            "temp_error": self.temp_error,
            "alive": True,
        }
        return bytes(json.dumps(data).encode("utf8"))

    def from_json(self, raw, challenge=None):
        """
        Recovers data from a JSON representation.
        This has two operational modes:

        If challenge is None it simply reads in the JSON
        data and sets internal state accordingly.

        When a challenge is passed, it uses the transportWrapper
        subsystem to ensure authenticty of message.
        """
        data = json.loads(raw)
        try:
            self.logger.debug("data={}".format(data))
            (self.state, self.batt_voltage, self.lamp_currents) = (
                data["state"],
                data["batt_voltage"],
                data["lamp_currents"],
            )
            (self.give_way, self.temp_error) = (data["give_way"], data["temp_error"])
        except KeyError as e:
            if not data["alive"]:
                self.logger.warning("Remote light has lost MQTT connection")
            else:
                raise e

    def set_config(self, param, value):
        # Dummy to be overloaded by real implementations
        pass

    def set_green(self, give_way):
        assert type(give_way) in (bool, int)
        give_way = bool(give_way)
        if self.give_way != give_way:
            if give_way:
                self.logger.debug("Should give way")
            else:
                self.logger.debug("Should CLOSE way")

            self.give_way = give_way
            self.send_update()

    def is_good(self):
        return (self.state != 9) and (self.seen())

    def set_temp_error(self, error_state):
        assert type(error_state) in (bool, int)
        error_state = bool(error_state)
        if self.temp_error != error_state:
            if error_state:
                self.logger.debug("Received temp error")
            else:
                self.logger.debug("No temp error")
            self.temp_error = error_state
            self.send_update()

    def __str__(self):
        return "TrafficLight(state={}, batt_voltage={}, lamp_currents={})".format(
            self.state, self.batt_voltage, self.lamp_currents
        )

    def reset(self):
        """
        Resets the traffic light
        """
        pass


class TrafficLightController(MQTTItem):
    plausible_ports = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyUSB2",
        "/dev/ttyACM0",
        "/dev/ttyACM1",
        "/dev/ttyACM2",
    ]

    def __init__(self, name, mqtt_param, port=None):
        MQTTItem.__init__(self, name, mqtt_param)
        self.port = port
        self.serial = None
        self.mqtt.subscribe("ampel/+/state")
        self.light_status = {}

    def _process_mqtt(self, client, user_data, message):
        print("TrafficLightController got ", str(message))
        m = re.search(r"ampel/(.[a-zA-Z0-9/]+)/state", message.topic)
        if m:
            name = m.group(0)
            self.light_status[name] = json.loads(message.body)

    def connect(self):
        ports = self.plausible_ports
        if self.port:
            ports = [self.port] + ports

        for name in ports:
            try:
                self.serial = serial.Serial(name, self.baud)
                self.rx_thread = threading.Thread(target=self._rx_thread, daemon=True)
                self.rx_thread.start()
                return True
            except serial.SerialException:
                continue
        return False

    def connectionLost(self):
        while not self.connect():
            time.sleep(0.5)

    def _rx_thread(self):
        while True:
            char = self.serial.read(1)
            self.char_received(char)

    def _tx_thread(self):
        while True:
            time.sleep(0.1)
            self.send_update()

    def char_received(self, char):
        char = char.decode("latin-1")
        logging.debug("TrafficLightController: received: {}".format(char))
        if char == "g":
            self.group.give_way = False
            self.group.temp_error = False
            self.group.send_update()
        elif char == "G":
            self.group.give_way = True
            self.group.temp_error = False
            self.group.send_update()

    def send_update(self):
        """
        Wakeup callback from group instance,
        send information to handheld
        """
        packet = ["1" if int(x) > 10 else "0" for x in self.group.lamp_currents]
        # FIXME: Classify Battery local/remote in good/bad
        packet += [str(self.group.state), str(self.group.batt_voltage)]
        cmd = " ".join(packet)
        self.sendLine(bytes(cmd.encode("ascii")))


class TrafficLightGroup:
    def __init__(self, local_name, port, remote_name, mqtt_param):
        self.local = TrafficLightSerial(local_name, mqtt_param, port)
        self.remote = TrafficLightRemote(remote_name, mqtt_param)
        self._check = threading.Thread(target=self._check_thread, daemon=True)
        self._check.start()
        self.logger = logging.getLogger("TrafficLightGroup")

    def __str__(self):
        return f"TrafficLightGroup(local={str(self.local)}, remote={str(self.remote)})"

    def mqtt_disconnect(self):
        self.remote.mqtt_disconnect()
        self.local.mqtt_disconnect()

    def seen(self):
        return self.local.seen() and self.remote.seen()

    def _check_thread(self):
        while True:
            time.sleep(1)
            self.check()

    def check(self):
        """
        Performs a routine sanity check of the system,
        copies external traffic lights state into own,
        if the remote state is known. Otherwise use local
        state
        """
        good = self.is_good()

        self.local.set_temp_error(not good)

        self.lamp_currents = self.local.lamp_currents + self.remote.lamp_currents

    def is_good(self):
        if not all([self.remote.seen(), self.local.seen()]):
            if not self.remote.seen():
                self.logger.debug("Remote not seen!")
            if not self.local.seen():
                self.logger.debug("Local not seen!")
            return False
        if 9 in [self.local.state, self.remote.state]:
            # If an error was detected on either side, fail here, too
            return False
        return True


class TrafficLightRemote(TrafficLight):
    """
    Interface to a remote traffic light.

    Gets remote's traffic light status via MQTT
    """

    def __init__(self, name, mqtt_param, interval=10):
        mqtt_param["name"] = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        TrafficLight.__init__(self, name, mqtt_param)

    def _do_subscriptions(self):
        self.logger.debug("subscribe to: %s", self.state_topic)
        self.mqtt.subscribe(self.state_topic)
        self.mqtt.message_callback_add(self.state_topic, self._process_mqtt_state)

    def _process_mqtt_state(self, client, user_data, message):
        self.logger.debug("TrafficLightRemote: got %s", message)
        self.from_json(message.payload)


class TrafficLightSerial(TrafficLight):
    delimiter = b"\n"

    config_map = {"min_on_current": 0, "max_on_current": 1, "max_off_current": 2}

    rx_timeout = 3

    baud = 19200

    def rx_thread(self):
        pass

    def __init__(self, name, mqtt_param, port, reset_pin=None):
        TrafficLight.__init__(self, name, mqtt_param)
        self.set_logger(logging.getLogger(name))
        self.ser = serial.Serial(port, self.baud)
        self.set_port(port)
        self.set_reset(reset_pin)
        self.send_update()
        self.rx_thread = threading.Thread(target=self._rx_thread, daemon=True)
        self.rx_thread.start()

    def _rx_thread(self):
        while True:
            line = self.ser.read_until()
            self.handle_line(line.decode("latin-1"))

    def handle_line(self, line):
        # Ignore blank lines
        if not line:
            return
        try:
            line = line.strip()
            (
                self.state,
                self.batt_voltage,
                self.error_state,
                self.lamp_currents[0],
                self.lamp_currents[1],
                self.lamp_currents[2],
            ) = line.split(" ")
            self.last_seen = time.time()
            self.publish()
        except (ValueError, UnicodeDecodeError):
            self.logger.info("Received garbled line")

    def reopen(self):
        """
        Establish a reader/writer thread
        """
        self.serial = serial.Serial(self.port, self.baud)
        self.send_update()

    def set_port(self, port):
        self.port = port

    def set_serial(self, serial):
        self.serial = serial

    def set_reset(self, pin):
        if pin is None:
            self.reset_name = None
            return

        self.reset_name = "/sys/class/gpio/gpio{}/value".format(pin)
        try:
            with open("/sys/class/gpio/export", "w") as f:
                f.write("{}\n".format(pin))
        except Exception as e:
            logging.error("Could not open/write exports in gpiofs: {}".format(e))

    def set_config(self, param, value):
        if param in self.config_map:
            cmd = "s{}={}".format(self.config_map[param], int(value))
            self.reader_thread.write(cmd.encode("ascii"))
        else:
            raise ValueError("Unknown parameter {}".format(param))

    def send_update(self):
        if self.give_way:
            self.ser.write("G".encode("ascii"))
        else:
            self.ser.write("g".encode("ascii"))
        if self.temp_error:
            self.ser.write("E".encode("ascii"))
        else:
            self.ser.write("e".encode("ascii"))

    def service_watchdog(self):
        self.send_update()


lightTypes = {
    "serial": TrafficLightSerial,
    "group": TrafficLightGroup,
    "remote": TrafficLightRemote,
}
