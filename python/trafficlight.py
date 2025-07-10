import json
import logging
import random
import os
from queue import Queue
from time import time
import serial
import threading


class TrafficLight:
    """
    Base class for traffic light implementation.
    This provides a skeleton for creating either physical
    interfaces or virtual traffic lights.
    """

    def __init__(self):
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

    def is_writable(self, key):
        """
        Test if this traffic light is writable from web interface.
        """
        if self.web_writeable:
            return True
        return False

    def dereference(self, names):
        """
        Dereferece symbolic names (if needed) after reading
        of config has been finished.
        """
        pass

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
    def open(cls, port, group):
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

    def __init__(self, i_am_master, local, remote, max_diverge=5):
        TrafficLight.__init__(self)
        self.i_am_master = i_am_master
        self.remote = remote
        self.local = local
        self.max_diverge = max_diverge
        self.start_diverge = None
        self.dereferenced = False
        self.controller = None

    def controllerLost(self):
        """
        Signals that the controller instance is now
        invalid.
        """
        self.controller = None

    def dereference(self, names):
        """
        Dereferece symbolic names (if needed)
        """
        if self.local in names:
            self.local = names[self.local]
        else:
            raise ValueError("Cannot find name {} for local.".format(self.local))

        if self.remote in names:
            self.remote = names[self.remote]
        else:
            raise ValueError("Cannot find name {} for remote.".format(self.remote))
        self.remote.setReadOnly(not self.i_am_master)
        self.web_writeable = self.i_am_master
        self.dereferenced = True

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
        if not self.dereferenced:
            logging.debug("Cannot check yet, not dereferenced yet")
            return None

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


class TrafficLightDummy(TrafficLight):
    @classmethod
    def open(cls, name, fail_probability):
        r = cls(float(fail_probability))
        r.set_logger(logging.getLogger(name))
        return r

    def __init__(self, fail_probability):
        TrafficLight.__init__(self)
        # self.fail_loop = task.LoopingCall(self.simulate_failures)
        # self.run_loop = task.LoopingCall(self.run)
        self.fail_probability = fail_probability
        self.state = 0
        self.fail_comm = False
        self.fail_lamp = False

        self.fail_loop.start(0.5).addErrback(self.error)
        self.run_loop.start(1).addErrback(self.error)

    def send_update(self):
        if self.read_only:
            self.logger.debug("Read-only: No update:")
        else:
            self.logger.debug("Would update: {}".format(self.state))

    def error(self, err):
        self.logger.debug(err)

    def simulate_failures(self):
        if random.random() > (1 - self.fail_probability):
            self.fail_lamp = random.random() > 0.5
            self.fail_comm = random.random() > 0.5
            self.logger.warning(
                "fail_lamp={} fail_comm={}".format(self.fail_lamp, self.fail_comm)
            )

    def reset(self):
        self.state = 0
        self.fail_comm = False
        self.fail_lamp = False

    def run(self):
        self.logger.debug("RUN")
        self.batt_voltage = 12 + random.random() * 1.5
        if not self.fail_comm:
            self.logger.debug("TICK")
            self.last_seen = time()
        if self.fail_lamp:
            self.state = 9
        self.logger.debug("state={} temp_error={}".format(self.state, self.temp_error))
        if self.state < 3:
            self.state += 1
        elif self.state == 5:
            if self.give_way:
                self.state = 6
        elif self.state == 6:
            self.state = 3
        elif self.state == 3:
            if not self.give_way:
                self.state = 4
        elif self.state == 4:
            self.state = 5
        elif self.state == 8 and self.temp_error == False:
            self.state = 3
        if self.temp_error:
            self.logger.warning("Got temporary error")
            self.state = 8
        self.lamp_currents = {
            0: [60, 0, 0],
            1: [60, 60, 0],
            2: [60, 60, 60],
            3: [0, 0, 60],
            4: [0, 60, 0],
            5: [60, 0, 0],
            6: [60, 60, 0],
            8: [0, 30, 0],
            9: [0, 25, 0],
        }[self.state]


class TrafficLightRemote(TrafficLight):
    """
    Interface to a remote traffic light.

    Uses the JSON GET/POST API and supports "signed"
    messages using the auth.transportWrapper for a bit
    better security.

    Note that only groups can be written remotely!!
    """

    @classmethod
    def open(cls, name, url, interval):
        r = cls(url, float(interval))
        r.set_logger(logging.getLogger(name))
        return r

    def __init__(self, url, interval):
        TrafficLight.__init__(self)
        self.poll_loop = task.LoopingCall(self.poll_remote)
        self.remote_url = url
        self.running_requests = {}
        self.error_count = 0
        self.request_count = 0
        self.poll_loop.start(interval).addErrback(log.err)

    def update_answer_handler(self, response):
        d = readBody(response)
        # TODO maybe move it until validation?
        self.error_count = 0
        d.addCallback(self.on_update_answer_received)
        d.addErrback(log.err)
        return d

    def on_update_answer_received(self, data):
        if not data.strip() == "ok":
            logging.error(
                "Something went wrong trying to update remote.. Answer was:{}".format(
                    data.strip()
                )
            )

    def poll_error(self, failure, starttime):
        """
        When a request fails, clean up the waiting list
        """
        self.logger.error("Request {} failed: {}".format(starttime, failure))
        self.error_count += 1
        del self.running_requests[starttime]

    def error_rate(self):
        if self.request_count > 0:
            return 100.0 * self.error_count / self.request_count
        else:
            return None

    def poll_remote(self):
        """
        Polls remote host to get its state
        """
        try:
            # FIXME: might fail on first iteration as transportWrapper is not
            #        yet initialized..
            self.request_count += 1
            challenge = self.transportWrapper.makeChallenge()
            url = (
                self.remote_url + "?" + urllib.parse.urlencode({"challenge": challenge})
            )
            url = bytes(url.encode("ascii"))
            starttime = time()
            req = self.agent.request(b"GET", url)
            req.addCallback(self.request_handler, challenge, starttime)
            req.addErrback(self.poll_error, starttime)
            self.running_requests[starttime] = req
            self.logger.debug(
                "len(running_requests)={}, age={:0.1f}s, error_rate={:0.2f}%".format(
                    len(self.running_requests),
                    time() - self.last_seen,
                    self.error_rate(),
                )
            )
        except Exception as e:
            self.logger.debug(">>>>{}".format(e))

    def force_set(self, giveway=None, temp_error=None):
        """
        Can be used to force remote's state to a certain value.
        Note this may fail if remote is not writable!
        """
        body = {}
        body["giveway"] = give_way

    def request_handler(self, response, challenge, starttime):
        d = readBody(response)
        # TODO maybe move it until validation?
        self.error_count = 0
        d.addCallback(self.on_data_received, challenge, starttime)
        d.addErrback(log.err)
        return d

    def on_data_received(self, body, challenge, starttime):
        if starttime not in self.running_requests:
            # This can only be triggered by a race condition between this
            # function cancelling a request and getting data. Not sure how
            # twisted handled this in the background, just catch it before
            # bad things happen
            self.logger.warning("State data arrived too late, discarding")
            return
        self.logger.debug("body={}".format(body))
        self.from_json(body, challenge)
        self.last_seen = starttime
        # Now purge old requests
        stale_requests = [
            started for started in self.running_requests if started < self.last_seen
        ]
        for started in stale_requests:
            self.running_requests[started].cancel()
            if started in self.running_requests:
                del self.running_requests[started]
            self.error_count += 1


class TrafficLightSerial(TrafficLight):
    delimiter = b"\n"

    config_map = {"min_on_current": 0, "max_on_current": 1, "max_off_current": 2}

    rx_timeout = 3

    baud = 19200

    def rx_thread(self):
        pass

    def __init__(self, name, port, reset_pin=None):
        TrafficLight.__init__(self)
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
    "dummy": TrafficLightDummy,
    "remote": TrafficLightRemote,
}
