import json
import logging
import random
import urllib.request, urllib.parse, urllib.error
import os
from twisted.internet.serialport import SerialPort
from twisted.internet import reactor, task
from twisted.web.client import Agent, readBody
from twisted.protocols import basic
from twisted.python import log
from time import time
from auth import TransportWrapper


class TrafficLight(object):
    '''
    Base class for traffic light implementation.
    This provides a skeleton for creating either physical
    interfaces or virtual traffic lights.
    '''

    def __init__(self):
        self.logger = logging.getLogger()
        self.state = 99
        self.batt_voltage = 0
        self.lamp_currents = [0]*3
        self.last_seen = 0
        self.maxage = 4
        self.give_way = True
        self.temp_error = False
        self.read_only = False
        self.web_writeable = False
        self.group_key = None
        self.transportWrapper = None

    def setGroupKey(self, key):
        '''
        Set shared secret (key) for all participants in
        the system.
        '''
        self.group_key = key
        self.transportWrapper = TransportWrapper(key)

    def isWritable(self, key):
        '''
        Test if this traffic light is writable from web interface.
        '''
        if self.web_writeable:
            return True
        if self.group_key is None:
            return False
        if self.group_key == key:
            return True
        return False

    def dereference(self, names):
        '''
        Dereferece symbolic names (if needed) after reading
        of config has been finished.
        '''
        pass

    def setLogger(self, logger):
        self.logger = logger

    def setReadOnly(self, read_only):
        self.read_only = read_only

    def seen(self):
        '''
        Test if the backend device has reported back
        in the last time within the self.maxage time frame
        '''
        return (time()-self.last_seen) < self.maxage

    def to_json(self, challenge):
        '''
        Returns the state of a traffic light in JSON
        format.
        If challenge is passed, the data packet it will be
        encapsulated in a TransportWrapper.
        '''
        data = {
            "state":self.state,
            "batt_voltage":self.batt_voltage,
            "lamp_currents":self.lamp_currents,
            "good":self.isGood(),
            "give_way":self.give_way,
            "temp_error":self.temp_error
            }
        if challenge is not None and self.transportWrapper is None:
            self.logger.error("missing transport wrapper")
        if challenge is not None and self.transportWrapper is not None:
            return bytes(self.transportWrapper.encapsulate(challenge, data).encode('utf8'))
        else:
            return bytes(json.dumps(data).encode('utf8'))

    def from_json(self, raw, challenge=None):
        '''
        Recovers data from a JSON representation.
        This has two operational modes:
        
        If challenge is None it simply reads in the JSON
        data and sets internal state accordingly.

        When a challenge is passed, it uses the transportWrapper
        subsystem to ensure authenticty of message.
        '''
        if challenge is None:
            data = json.loads(raw)
        else:
            data = self.transportWrapper.decapsulate(raw, challenge)
        self.logger.debug("data={}".format(data))
        if data is None:
            self.logger.error("Transport failed")
        (self.state, self.batt_voltage, self.lamp_currents) = (data["state"],
                                                               data["batt_voltage"],
                                                               data["lamp_currents"]
                                                               )
        (self.give_way, self.temp_error) = (data["give_way"], data["temp_error"])

    def setConfig(self, param, value):
        # Dummy to be overloaded by real implementations
        pass

    def setGreen(self, give_way):
        assert type(give_way) in (bool, int)
        give_way = bool(give_way)
        if self.give_way != give_way:
            if give_way:
                self.logger.debug("Should give way")
            else:
                self.logger.debug("Should CLOSE way")

            self.give_way = give_way
            self.sendUpdate()

    def isGood(self):
        return (self.state != 9) and (self.seen())

    def setTempError(self, error_state):
        assert type(error_state) in (bool, int)
        error_state = bool(error_state)
        if self.temp_error != error_state:
            if error_state:
                self.logger.debug("Received temp error")
            else:
                self.logger.debug("No temp error")
            self.temp_error = error_state
            self.sendUpdate()

    def __str__(self):
        return "TrafficLight(state={}, batt_voltage={}, lamp_currents={})".format(self.state, self.batt_voltage, self.lamp_currents)

    def reset(self):
        '''
        Resets the traffic light
        '''
        pass


class TrafficLightController(basic.LineReceiver):
    @classmethod
    def open(cls, port, group):
        controller = cls()
        serial = SerialPort(baudrate=19200, deviceNameOrPortNumber=port,
                            protocol=controller, reactor=reactor)
        controller.setSerial(serial)
        controller.setGroup(group)
        return controller

    def connectionLost(self, reason):
        # Declare myself lost to group
        self.group.controllerLost()

    def setSerial(self, serial):
        self.serial = serial

    def setGroup(self, group):
        self.group = group

    def lineReceived(self, line):
        line = line.decode('utf-8')
        logging.debug("TrafficLightController: received: {}".format(line))
        for c in line:
            if c == "g":
                self.group.give_way = False
                self.group.temp_error = False
                self.group.sendUpdate()
            elif c == "G":
                self.group.give_way = True
                self.group.temp_error = False
                self.group.sendUpdate()
            # TODO: Should we really discard siently?

    def sendUpdate(self):
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
    controller_devs = ["{}{}".format(prefix, i)
                        for i in range(5)
                        for prefix in ["/dev/ttyUSB", '/dev/ttyACM']
                        ]

    @classmethod
    def open(cls, name, i_am_master, local, remote, max_diverge=10,
             group_key=None):
        if str(i_am_master).upper() in ("YES", "TRUE", "1"):
            i_am_master = True
        else:
            i_am_master = False
        r = cls(i_am_master, local, remote, group_key, max_diverge)
        r.setLogger(logging.getLogger(name))
        return r

    def __init__(self, i_am_master, local, remote, group_key, max_diverge=5):
        TrafficLight.__init__(self)
        self.i_am_master = i_am_master
        self.remote = remote
        self.local = local
        self.max_diverge = max_diverge
        self.start_diverge = None
        self.dereferenced = False
        self.setGroupKey(group_key)
        self.check_loop = task.LoopingCall(self.check)
        self.check_loop.start(.25).addErrback(log.err)
        self.controller = None

    def controllerLost(self):
        '''
        Signals that the controller instance is now
        invalid.
        '''
        self.controller = None

    def dereference(self, names):
        '''
        Dereferece symbolic names (if needed)
        '''
        if self.local in names:
            self.local = names[self.local]
        else:
            raise ValueError("Cannot find name {} for local.".format(self.local))

        if self.remote in names:
            self.remote = names[self.remote]
        else:
            raise ValueError("Cannot find name {} for remote.".format(self.remote))
        self.remote.setReadOnly(not self.i_am_master)
        self.remote.setGroupKey(self.group_key)
        self.local.setGroupKey(self.group_key)
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
                    self.logger.error("Opening path {} as a controller failed: {}"
                                      .format(path, e))

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

        good = self.isGood()
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
            self.logger.info("Will try to sync from master remote.give_way={}, remote.temp_error={}".format(self.remote.give_way, self.remote.temp_error))
            # In case we don't have a local error, check remote side
            # if something is wrong there.
            if good in (True, None) and not self.i_am_master:
                temperr = self.remote.temp_error
            self.setGreen(self.remote.give_way)
            self.sendUpdate()

        # If we don't see the remote, use local voltage for
        # the groups voltage/state for now.
        # FIXME: Maybe take the worst of all states so the
        #        state information is more pessimistic.
        if self.remote.seen():
            source = self.remote
        else:
            source = self.local

        self.setTempError(temperr)
        self.state = source.state
        self.lamp_currents = self.local.lamp_currents + self.remote.lamp_currents

    def setTempError(self, state):
        self.temp_error = state
        self.sendUpdate()

    def sendUpdate(self):
        self.local.setGreen(self.give_way)
        self.local.setTempError(self.temp_error)
        # Try to update the manual controller
        if self.controller is not None:
            self.controller.sendUpdate()

    def isGood(self):
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
        r.setLogger(logging.getLogger(name))
        return r

    def __init__(self, fail_probability):
        TrafficLight.__init__(self)
        self.fail_loop = task.LoopingCall(self.simulateFailures)
        self.run_loop = task.LoopingCall(self.run)
        self.fail_probability = fail_probability
        self.state = 0
        self.fail_comm = False
        self.fail_lamp = False

        self.fail_loop.start(.5) .addErrback(self.error)
        self.run_loop.start(1) .addErrback(self.error)

    def sendUpdate(self):
        if self.read_only:
            self.logger.debug("Read-only: No update:")
        else:
            self.logger.debug("Would update: {}".format(self.state))

    def error(self, err):
        self.logger.debug(err)

    def simulateFailures(self):
        if random.random() > (1 - self.fail_probability):
            self.fail_lamp = random.random() > .5
            self.fail_comm = random.random() > .5
            self.logger.warning("fail_lamp={} fail_comm={}".format(self.fail_lamp, self.fail_comm))

    def reset(self):
        self.state = 0
        self.fail_comm = False
        self.fail_lamp = False

    def run(self):
        self.logger.debug("RUN")
        self.batt_voltage = 12 + random.random()*1.5
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
    '''
    Interface to a remote traffic light.

    Uses the JSON GET/POST API and supports "signed"
    messages using the auth.transportWrapper for a bit
    better security.

    Note that only groups can be written remotely!!
    '''

    @classmethod
    def open(cls, name, url, interval):
        r = cls(url, float(interval))
        r.setLogger(logging.getLogger(name))
        return r

    def __init__(self, url, interval):
        TrafficLight.__init__(self)
        self.poll_loop = task.LoopingCall(self.poll_remote)
        self.agent = Agent(reactor)
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
            logging.error("Something went wrong trying to update remote.. Answer was:{}".format(data.strip()))

    def poll_error(self, failure, starttime):
        '''
        When a request fails, clean up the waiting list
        '''
        self.logger.error("Request {} failed: {}".format(starttime, failure))
        self.error_count += 1
        del self.running_requests[starttime]

    def error_rate(self):
        if self.request_count > 0:
            return 100. * self.error_count / self.request_count
        else:
            return None

    def poll_remote(self):
        '''
        Polls remote host to get its state
        '''
        try:
            # FIXME: might fail on first iteration as transportWrapper is not
            #        yet initialized..
            self.request_count += 1
            challenge = self.transportWrapper.makeChallenge()
            url = self.remote_url + "?" + urllib.parse.urlencode({"challenge": challenge})
            url = bytes(url.encode("ascii"))
            starttime = time()
            req = self.agent.request(b"GET", url)
            req.addCallback(self.request_handler, challenge, starttime)
            req.addErrback(self.poll_error, starttime)
            self.running_requests[starttime] = req
            self.logger.debug("len(running_requests)={}, age={:0.1f}s, error_rate={:0.2f}%".format(len(self.running_requests), time()-self.last_seen, self.error_rate()))
        except Exception as e:
            self.logger.debug(">>>>{}".format(e))

    def force_set(self, giveway=None, temp_error=None):
        '''
        Can be used to force remote's state to a certain value.
        Note this may fail if remote is not writable!
        '''
        body = {}
        body['giveway'] = give_way


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
        stale_requests = [ started for started in self.running_requests if started < self.last_seen ]
        for started in stale_requests:
            self.running_requests[started].cancel()
            if started in self.running_requests:
                del self.running_requests[started]
            self.error_count += 1


class TrafficLightSerial(basic.LineReceiver, TrafficLight):

    delimiter = '\n'.encode('ascii')

    config_map = {"min_on_current": 0,
                  "max_on_current": 1,
                  "max_off_current": 2
                  }

    rx_timeout = 3

    baud = 19200

    @classmethod
    def open(cls, name, port, reset_pin=None, reactor=reactor):
        local_light = cls()
        local_light.setLogger(logging.getLogger(name))
        serial = SerialPort(baudrate=cls.baud, deviceNameOrPortNumber=port,
                            protocol=local_light, reactor=reactor)
        local_light.setSerial(serial)
        local_light.setPort(port)
        local_light.setReset(reset_pin)
        local_light.reactor = reactor
        local_light.sendUpdate()
        #reactor.call_later(cls.rx_timeout, local_light.timed_out)
        return local_light


    def reopen(self):
        '''
        Tries to reestablish a serial link in case of HW issues
        '''
        print(dir(self.serial))

        self.serial = SerialPort(baudrate=self.baud, deviceNameOrPortNumber=self.port,
                            protocol=self, reactor=self.reactor)

    def lineLengthExceeded(self, line):
        logging.error("Line length exceeded/codeDecodeErrorbaud rate error?")
        print(self.serial)
        self.serial.loseConnection()
        self.serial.stopReading()
        self.reactor.callLater(1, self.reopen)
        #self.reopen()

    def setPort(self, port):
        self.port = port

    def setSerial(self, serial):
        self.serial = serial

    def setReset(self, pin):
        if pin is None:
            self.reset_name = None
            return

        self.reset_name = "/sys/class/gpio/gpio{}/value".format(pin)
        try:
            with open("/sys/class/gpio/export", "w") as f:
                f.write("{}\n".format(pin))
        except Exception as e:
            logging.error("Could not open/write exports in gpiofs: {}".format(e))

    def lineReceived(self, line):
        # Ignore blank lines
        if not line:
            return
        try:
            line = line.decode("ascii").strip()
            (self.state, self.batt_voltage, self.error_state, self.lamp_currents[0], self.lamp_currents[1], self.lamp_currents[2]) = line.split(" ")
            self.last_seen = time()
        except (ValueError, UnicodeDecodeError):
            logging.info("Received garbled line")
        # logging.warning("update myself: {}".format(self))

    def setConfig(self, param, value):
        if param in self.config_map:
            cmd = "s{}={}".format(self.config_map[param], int(value))
            self.sendLine(cmd)
        else:
            raise ValueError("Unknown parameter {}".format(param))

    def sendUpdate(self):
        if self.give_way:
            self.sendLine("G".encode("ascii"))
        else:
            self.sendLine("g".encode("ascii"))
        if self.temp_error:
            self.sendLine("E".encode("ascii"))
        else:
            self.sendLine("e".encode("ascii"))

    def serviceWatchdog(self):
        self.sendUpdate()


lightTypes = {'serial': TrafficLightSerial,
              'group': TrafficLightGroup,
              'dummy': TrafficLightDummy,
              'remote': TrafficLightRemote,
              }
