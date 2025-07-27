import json
import logging
import os
import re
import random
import time
import serial
import threading
import queue
import os
import paho.mqtt.client as mqtt

except_queue = queue.Queue()


def thread_except(args):
    import traceback

    print(args.exc_type, args.exc_value)
    traceback.print_tb(args.exc_traceback)
    os._exit(-1)


threading.excepthook = thread_except


class MQTTItem:
    def __init__(self, name, mqtt_param, anonymous=False):
        self.mqtt_param = mqtt_param
        self.name = name
        self._shutdown = False
        self._anonymous = anonymous
        self._connected = False
        self.state_topic = f"ampel/{self.name}/state"
        self.command_topic = "ampel/command"
        try:
            self._connect_mqtt()
        except OSError:
            # In case MQTT does not come up, run helper in background
            self.retry_thread = threading.Thread(
                target=self._retry_connect_mqtt, daemon=True
            )
            self.retry_thread.start()

    def _retry_connect_mqtt(self):
        # Thread called in case MQTT does not connect immediately
        while True:
            time.sleep(1)
            try:
                self._connect_mqtt()
                # On success -> exit
                return
            except OSError:
                # In case MQTT does not come up
                pass

    def _connect_mqtt(self):
        mqtt_param = self.mqtt_param
        if mqtt_param:
            # For clients with temporary name (listeners)
            if not self._anonymous:
                if "name" in mqtt_param:
                    name = mqtt_param["name"]
                else:
                    name = self.name
            else:
                name = None
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
        self.logger.debug(self.name + " MQTT Connected")
        self._do_subscriptions()

    def _do_subscriptions(self):
        self.logger.debug("Subscribe command")
        self.mqtt.subscribe(self.command_topic)

    def _mqtt_disconnected(self, client, userdata, rc, x=None, y=None, z=None):
        self.logger.debug(" MQTT disconnect: %s", rc)

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

    def shutdown(self):
        self._shutdown = True
        self.mqtt_disconnect()


class TrafficLight(MQTTItem):
    """
    Base class for traffic light implementation.
    This provides a skeleton for creating either physical
    interfaces or virtual traffic lights.
    """

    def __init__(self, name, mqtt_param, local=True):
        logname = name
        if not local:
            logname = "remote-" + logname

        self.logger = logging.getLogger(logname)
        MQTTItem.__init__(self, name, mqtt_param, anonymous=not local)
        self.state = 99
        self.batt_voltage = 0
        self.lamp_currents = [0] * 3
        self.last_seen = 0
        self.maxage = 4
        self.give_way = True
        self.temp_error = False

    def __set__(self):
        return f"TrafficLight(name={self.name}, self.lamp_currents)"

    def _process_mqtt_command(self, client, user_data, message):
        self.logger.debug("TrafficLight got: %s ", message)
        try:
            cmd = json.loads(message.payload)
        except json.JSONDecodeError:
            self.logger.warning("Could not parse command JSON: %s", message.payload)
            return
        self.set_green(cmd["give_way"])

    def publish(self):
        self.logger.debug(self.state)
        try:
            self.mqtt.publish(self.state_topic, self.to_json())
        except AttributeError as e:
            """ If there is no MQTT connection, disregard """
            pass

    def set_logger(self, logger):
        self.logger = logger

    def seen(self):
        """
        Test if the backend device has reported back
        in the last time within the self.maxage time frame
        """
        self.logger.debug("Last seen since: %d", time.time() - self.last_seen)
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
            "last_seen": self.last_seen,
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
            (self.give_way, self.temp_error, self.last_seen, self._is_good) = (
                data["give_way"],
                data["temp_error"],
                data["last_seen"],
                data["good"],
            )
        except KeyError as e:
            if "alive" in data and not data["alive"]:
                self.logger.warning("Remote light has lost MQTT connection")
            else:
                self.logger.error("Bad state received")

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
                self.logger.info("Received temp error")
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

    def _do_subscriptions(self):
        MQTTItem._do_subscriptions(self)
        self.mqtt.message_callback_add(self.command_topic, self._process_mqtt_command)


class TrafficLightController(MQTTItem):
    plausible_ports = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyUSB2",
        "/dev/ttyACM0",
        "/dev/ttyACM1",
        "/dev/ttyACM2",
    ]
    baud = 19200

    def __init__(self, name, mqtt_param, port=None):
        self.logger = logging.getLogger(name)
        MQTTItem.__init__(self, name, mqtt_param)
        self.port = port
        self.serial = None
        self.light_status = {}
        self.ok = False

    def _do_subscriptions(self):
        self.logger.debug("Adding subscritions")
        self.mqtt.subscribe("ampel/+/state")
        self.mqtt.message_callback_add("ampel/+/state", self.handle_state)

    def handle_state(self, client, user_data, message):
        logging.debug("TrafficLightController got ", str(message))
        m = re.search(r"ampel/(.[a-zA-Z0-9/]+)/state", message.topic)
        if m:
            name = m.group(0)
            try:
                self.light_status[name] = json.loads(message.payload)
            except json.JSONDecodeError:
                self.logger.error("Could not decode %s for %s", message.payload, name)

    def connect(self):
        ports = self.plausible_ports
        if self.port:
            ports = [self.port] + ports
        self._shutdown = False

        for name in ports:
            try:
                self.serial = serial.Serial(name, self.baud)
                self.rx_thread = threading.Thread(target=self._rx_thread, daemon=True)
                self.rx_thread.start()
                self.tx_thread = threading.Thread(target=self._tx_thread, daemon=True)
                self.tx_thread.start()
                self.ok = True
                return True
            except serial.SerialException:
                continue
        return False

    def shutdown(self):
        self.logger.debug("Shutdown!")
        self._shutdown = True

    def _rx_thread(self):
        while not self._shutdown:
            try:
                char = self.serial.read(1)
                if not len(char):
                    self._shutdown = True
                    self.ok = False
            except serial.SerialException:
                self.ok = False
                self._shutdown = True
            if char:
                self.char_received(char)

    def _tx_thread(self):
        while not self._shutdown:
            time.sleep(0.2)
            self.send_update()

    def publish(self, give_way):
        payload = json.dumps({"give_way": bool(give_way)})
        try:
            self.mqtt.publish(self.command_topic, payload, retain=True)
            self.logger.debug("Published command!")
        except AttributeError as e:
            """ If there is no MQTT connection, disregard """
            pass

    def char_received(self, char):
        char = char.decode("latin-1")
        self.logger.debug("TrafficLightController: received: {}".format(char))
        if char == "g":
            self.publish(False)
            # self.group.send_update()
        elif char == "G":
            self.publish(True)
            # self.group.send_update()

    def send_update(self):
        """
        Wakeup callback from group instance,
        send information to handheld
        """
        # FIXME: Get actual currents
        currents = 6 * [0]
        packet = ["1" if int(x) > 10 else "0" for x in currents]
        # FIXME: Classify Battery local/remote in good/bad
        # packet += [str(self.group.state), str(self.group.batt_voltage)]
        cmd = " ".join(packet) + "\r\n"
        try:
            self.serial.write(bytes(cmd.encode("ascii")))
        except serial.SerialException:
            self.ok = False
            self._shutdown = True


class TrafficLightGroup:
    def __init__(self, local_name, port, remote_name, mqtt_param):
        self._shutdown = False
        self.local = TrafficLightSerial(local_name, mqtt_param, port)
        self.remote = TrafficLightRemote(remote_name, mqtt_param)
        self._check = threading.Thread(target=self._check_thread, daemon=True)
        self._check.start()
        self.logger = logging.getLogger("TrafficLightGroup " + local_name)

    def __str__(self):
        return f"TrafficLightGroup(local={str(self.local)}, remote={str(self.remote)})"

    def shutdown(self):
        self._shutdown = True
        self.remote.shutdown()
        self.logger.debug("Shutting down local")
        self.local.shutdown()
        self.logger.debug("Stopping check")

    def seen(self):
        return self.local.seen() and self.remote.seen()

    def _check_thread(self):
        while not self._shutdown:
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
        if not good:
            self.logger.debug("Not good!")
        else:
            self.logger.debug("Good")
        self.local.set_temp_error(not good)
        self.lamp_currents = self.local.lamp_currents + self.remote.lamp_currents
        """
        print(
            self.lamp_currents,
            self.local.temp_error,
            self.remote.temp_error,
            self.local.is_good(),
            self.remote.is_good(),
        )
        """

    def is_good(self):
        if not all([self.remote.seen(), self.local.seen()]):
            if not self.remote.seen():
                self.logger.debug("Remote not seen!")
            if not self.local.seen():
                self.logger.debug("Local not seen!")
            return False
        if 9 in [self.local.state, self.remote.state]:
            self.logger.debug("Error state seen!")
            # If an error was detected on either side, fail here, too
            return False
        return True


class TrafficLightRemote(TrafficLight):
    """
    Interface to a remote traffic light.

    Gets remote's traffic light status via MQTT
    """

    def __init__(self, name, mqtt_param, interval=10):
        self._is_good = False
        if mqtt_param is not None:
            mqtt_param["name"] = "".join(
                random.choices("abcdefghijklmnopqrstuvwxyz", k=10)
            )
        TrafficLight.__init__(self, name, mqtt_param, local=False)
        self.mqtt.message_callback_add(self.state_topic, self._process_mqtt_state)

    def _do_subscriptions(self):
        self.logger.debug("subscribe to: %s", self.state_topic)
        self.mqtt.subscribe(self.state_topic)

    def _process_mqtt_state(self, client, user_data, message):
        self.logger.debug("Message : %s", message.payload)
        self.from_json(message.payload)
        # self.last_seen = time.time()

    def publish(self):
        assert False, "Should never be called"

    def is_good(self):
        return self._is_good


class TrafficLightSerial(TrafficLight):
    delimiter = b"\n"

    config_map = {"min_on_current": 0, "max_on_current": 1, "max_off_current": 2}

    rx_timeout = 3

    baud = 19200

    def rx_thread(self):
        pass

    def __init__(self, name, mqtt_param, port, reset_pin=None):
        TrafficLight.__init__(self, name, mqtt_param)
        self.rx_err = 0
        self.set_logger(logging.getLogger(name))
        self.ser = serial.Serial(port, self.baud, timeout=2)
        self.set_port(port)
        self.set_reset(reset_pin)
        self.send_update()
        self.rx_thread = threading.Thread(target=self._rx_thread, daemon=True)
        self.rx_thread.start()
        self.tx_thread = threading.Thread(target=self._tx_thread, daemon=True)
        self.tx_thread.start()

    def _rx_thread(self):
        while not self._shutdown:
            line = self.ser.read_until(size=80)
            self.handle_line(line.decode("latin-1"))

    def _tx_thread(self):
        while not self._shutdown:
            time.sleep(5)
            self.send_update()

    def handle_line(self, line):
        # Ignore blank lines
        if not line:
            self.err()
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
            self.state = int(self.state)
            self.last_seen = time.time()

            self.publish()
            self.rx_err = 0
        except (ValueError, UnicodeDecodeError) as e:
            self.err()
            self.logger.info(
                "Received garbled line: %d -  %s: %s", self.rx_err, line, e
            )

    def err(self):
        self.rx_err += 1
        if self.rx_err > 10:
            self.reopen()
            self.rx_err = 0

    def reopen(self):
        """
        Establish a reader/writer thread
        """
        self.ser.close()
        serial.Serial(self.port, 9600).close()
        time.sleep(1)
        self.ser = serial.Serial(self.port, self.baud, timeout=1)
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
            self.logger.error("Could not open/write exports in gpiofs: {}".format(e))

    def set_config(self, param, value):
        if param in self.config_map:
            cmd = "s{}={}".format(self.config_map[param], int(value))
            self.reader_thread.write(cmd.encode("ascii"))
        else:
            raise ValueError("Unknown parameter {}".format(param))

    def send_update(self):
        self.logger.debug("send_update: give_way=%s", self.give_way)
        cmd = b""
        if self.give_way:
            cmd += b"G"
        else:
            cmd += b"g"
        if self.temp_error:
            cmd += b"E"
        else:
            cmd += b"e"
        self.logger.debug("Sending: %s", cmd)
        try:
            self.ser.write(cmd)
        except serial.PortNotOpenError:
            # Disregard, we're reconnecting ..
            pass

    def shutdown(self):
        TrafficLight.shutdown(self)
        self.logger.debug("Stopping tx thread")
        self.rx_thread.stop()
        self.logger.debug("Stopping rx thread")
        self.tx_thread.stop()
        self.logger.debug("Closing serial")
        self.ser.close()


lightTypes = {
    "serial": TrafficLightSerial,
    "group": TrafficLightGroup,
    "remote": TrafficLightRemote,
}
