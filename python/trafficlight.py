import json
import logging
import os
from time import time
import serial
import threading
import paho.mqtt.client as mqtt


class TrafficLight:
    """
    Base class for traffic light implementation.
    This provides a skeleton for creating either physical
    interfaces or virtual traffic lights.
    """

    def __init__(self, name, mqtt_param):
        self.mqtt_param = mqtt_param
        self.logger = logging.getLogger()
        self.state = 99
        self.batt_voltage = 0
        self.lamp_currents = [0] * 3
        self.last_seen = 0
        self.maxage = 4
        self.give_way = True
        self.temp_error = False
        self.read_only = False
        self.web_writeable = False
        self.name = name
        self._connect_mqtt()

    def _connect_mqtt(self):
        mqtt_param = self.mqtt_param
        if mqtt_param:
            self.mqtt = mqtt.Client(client_id=self.name)
            self.mqtt.username_pw_set(
                username=mqtt_param["username"], password=mqtt_param["password"]
            )
            # Try to reconnect if connection fails
            self.mqtt.on_message = self._process_mqtt
            self.mqtt.connect(mqtt_param["host"], mqtt_param["port"])
            # TODO Enable TLS if necessary!!!
            self.state_topic = f"ampel/{self.name}/state"
            self.mqtt.loop_start()

        else:
            self.mqtt = None

    def _process_mqtt(self, client, user_data, message):
        # TODO: Implement processing of messages
        if message.topic == "info":
            print(message.payload)
            pass

    def publish(self):
        try:
            self.mqtt.publish(self.state_topic, self.to_json())
        except AttributeError as e:
            print(e)
            """ If there is no MQTT connection, disregard """
            pass

    def is_writable(self, key):
        """
        Test if this traffic light is writable from web interface.
        """
        if self.web_writeable:
            return True
        return False

    def set_logger(self, logger):
        self.logger = logger

    def set_read_only(self, read_only):
        self.read_only = read_only

    def seen(self):
        """
        Test if the backend device has reported back
        in the last time within the self.maxage time frame
        """
        return (time() - self.last_seen) < self.maxage

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
        self.logger.debug("data={}".format(data))
        (self.state, self.batt_voltage, self.lamp_currents) = (
            data["state"],
            data["batt_voltage"],
            data["lamp_currents"],
        )
        (self.give_way, self.temp_error) = (data["give_way"], data["temp_error"])

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


class TrafficLightController:
    @classmethod
    def open(cls, port, group, mqtt_param):
        controller = cls()
        ser = serial.serial_for_url(port, baudrate=19200, timeout=1)
        controller.set_serial(ser)
        controller.setGroup(group)
        return controller

    def connectionLost(self, reason):
        # Declare myself lost to group
        self.group.controllerLost()

    def set_serial(self, serial):
        self.serial = serial

    def setGroup(self, group):
        self.group = group

    def line_received(self, line):
        line = line.decode("latin-1")
        logging.debug("TrafficLightController: received: {}".format(line))
        for c in line:
            if c == "g":
                self.group.give_way = False
                self.group.temp_error = False
                self.group.send_update()
            elif c == "G":
                self.group.give_way = True
                self.group.temp_error = False
                self.group.send_update()
            # TODO: Should we really discard siently?

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


class TrafficLightGroup(TrafficLight):
    # Names of all controller files to be scanned
    controller_devs = [
        "{}{}".format(prefix, i)
        for i in range(5)
        for prefix in ["/dev/ttyUSB", "/dev/ttyACM"]
    ]

    @classmethod
    def open(cls, name, i_am_master, local, remote, max_diverge=10):
        if str(i_am_master).upper() in ("YES", "TRUE", "1"):
            i_am_master = True
        else:
            i_am_master = False
        r = cls(i_am_master, local, remote, max_diverge)
        r.set_logger(logging.getLogger(name))
        return r

    def __init__(self, name, mqtt_param, i_am_master, local, remote, max_diverge=5):
        TrafficLight.__init__(self, name, mqtt_param)
        self.i_am_master = i_am_master
        self.remote = remote
        self.local = local
        self.max_diverge = max_diverge
        self.start_diverge = None
        self.controller = None

    def controllerLost(self):
        """
        Signals that the controller instance is now
        invalid.
        """
        self.controller = None

    def seen(self):
        return self.local.seen() and self.remote.seen()

    def probe_controller(self):
        """
        Tries to find a controller by rotating the
        list of known file names and trying to access them
        """
        # Process a whole list of options
        for path in self.controller_devs:
            self.logger.debug("Try '{}'".format(path))
            if os.path.exists(path):
                self.logger.debug("'{}' exists".format(path))
                try:
                    self.controller = TrafficLightController.open(path, self)

                except Exception as e:
                    self.logger.error(
                        "Opening path {} as a controller failed: {}".format(path, e)
                    )

    def check(self):
        """
        Performs a routine sanity check of the system,
        copies external traffic lights state into own,
        if the remote state is known. Otherwise use local
        state
        """
        if self.i_am_master and self.controller is None:
            # Probe for external controller if none is attached (yet)
            self.probe_controller()
            pass

        good = self.is_good()
        temperr = self.temp_error

        if good is False:
            temperr = True
            self.logger.error("Temporary error")
        elif good is None:
            self.logger.info("Diverged, try to realign")
        else:
            self.logger.info("good")
            temperr = False

        if self.remote.seen() and not self.i_am_master:
            self.logger.info(
                "Will try to sync from master remote.give_way={}, remote.temp_error={}".format(
                    self.remote.temp_error, self.remote.give_way
                )
            )
            # In case we don't have a local error, check remote side
            # if something is wrong there.
            if good in (True, None) and not self.i_am_master:
                temperr = self.remote.temp_error
            self.set_green(self.remote.give_way)
            self.send_update()

        # If we don't see the remote, use local voltage for
        # the groups voltage/state for now.
        # FIXME: Maybe take the worst of all states so the
        #        state information is more pessimistic.
        if self.remote.seen():
            source = self.remote
        else:
            source = self.local

        self.set_temp_error(temperr)
        self.state = source.state
        self.lamp_currents = self.local.lamp_currents + self.remote.lamp_currents

    def set_temp_error(self, state):
        self.temp_error = state
        self.send_update()

    def send_update(self):
        self.local.set_green(self.give_way)
        self.local.set_temp_error(self.temp_error)
        # Try to update the manual controller
        if self.controller is not None:
            self.controller.send_update()

    def is_good(self):
        if False in [self.remote.seen(), self.local.seen()]:
            if not self.remote.seen():
                self.logger.debug("Remote not seen!")
            if not self.local.seen():
                self.logger.debug("Local not seen!")
            return False
        # In transistions, disregard state divergence for a while
        if self.remote.give_way != self.local.give_way:
            if self.start_diverge is None:
                self.start_diverge = time()
            if (time() - self.start_diverge) > self.max_diverge:
                return "maxdiverge"
                return False
            return None
        else:
            self.start_diverge = None
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
        TrafficLight.__init__(self, name, mqtt_param)
        self.mqtt.subscribe(self.state_topic)

    def _process_mqtt(self, client, user_data, message):
        if message.topic == self.state_topic:
            self.from_json(message.body)


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
            self.last_seen = time()
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
