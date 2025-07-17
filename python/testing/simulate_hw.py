import os
import threading
import time
import pty
import select
import logging

STATE_MAP = {
    "TRAFFIC_TEST_RED": 0,
    "TRAFFIC_TEST_RED_YELLOW": 1,
    "TRAFFIC_TEST_RED_YELLOW_GREEN": 2,
    "TRAFFIC_GREEN": 3,
    "TRAFFIC_YELLOW": 4,
    "TRAFFIC_RED": 5,
    "TRAFFIC_RED_YELLOW": 6,
    "TRAFFIC_TEMP_ERROR_DARK": 7,
    "TRAFFIC_TEMP_ERROR": 8,
    "TRAFFIC_FAIL": 9,
}


class SimBase:
    def __init__(self):
        """
        Initializes a simulator.

        Brings up the pts, sets self.pts with is the path of the pts to be used
        by clients and sets up the pipe.
        Also starts up a thread for handling input from clients.
        """
        # self.pts, self.pipe, self.poll =
        self._get_pts()
        self.ready = False
        self._shutdown = False
        self._reader_task = threading.Thread(target=self.reader_task, daemon=True)
        self._reader_task.start()
        self._main_task = threading.Thread(target=self.main, daemon=True)
        self._main_task.start()

    def _get_pts(self):
        """
        Allocates a pts device, enable its io and return both the name
        of the newly opened pts and the pipe for own use
        """
        (master, slave) = pty.openpty()
        self.pts = os.ttyname(slave)

        # Open and close to force HUP flag!
        os.close(slave)

        pollobject = select.epoll()
        pollobject.register(master, select.POLLHUP | select.POLLIN | select.EPOLLET)

        self.pipe = master
        self.poll = pollobject

    def reader_task(self):
        """
        Hande reading from the newly generated pts.
        NOTE: This a subtile bug, in that it will only start to work if one byte
              has been received. So one needs to send at least one byte for this
              emulator to start up.
        """
        while True:
            tuples = self.poll.poll(None)
            for fd, events in tuples:
                if events & select.POLLHUP:
                    self.ready = False
                    continue
                else:
                    self.ready = True

                if events & select.POLLIN:
                    data = os.read(self.pipe, 10)
                    for char in data.decode("latin-1"):
                        self.process(char)

    def process(self, line):
        pass

    def main(self):
        while not self._shutdown:
            time.sleep(1)


class SimController(SimBase):
    def __init__(self):
        SimBase.__init__(self)

    def main(self):
        while not self._shutdown:
            time.sleep(1)
            os.write(self.pipe, b".")

    def process(self, char):
        # print(char)
        pass

    def press_green(self):
        os.write(self.pipe, b"G\n")

    def press_red(self):
        logging.info("Press red")
        os.write(self.pipe, b"g\n")


class SimLight(SimBase):
    second = 10

    def __init__(self):
        SimBase.__init__(self)
        self.serial_state = "SERIAL_IDLE"
        self.traffic_state = "TRAFFIC_TEST_RED"
        self.request_green = False
        self.request_temp_error = False
        self.batt_voltage = 13.7
        self.discarge_rate = 1e-3 / self.second
        self.bulb_resistance = {"red": 1, "yellow": 1, "green": 1}
        self.sense = {"red": 0, "yellow": 0, "green": 0}
        self.pulse = 0
        self.analog_cycles = 0
        self.error_state = 0
        self.enable = False
        self.red = 0
        self.yellow = 0
        self.green = 0

    def process(self, line):
        """Emulate the "serial_statemachine" for the JAL-Firmware"""
        for tmp in line.strip():
            if not self.enable:
                continue
            if self.serial_state == "SERIAL_IDLE":
                if tmp == "G":
                    self.request_green = True
                if tmp == "g":
                    self.request_green = False
                if tmp == "E":
                    self.request_temp_error = True
                if tmp == "e":
                    self.request_temp_error = False
                if ((tmp == "\r") | (tmp == "\n")) & (
                    self.serial_state == "SERIAL_READ_DATA"
                ):
                    self.serial_state = "SERIAL_IDLE"
                if ord(tmp) == 27:
                    self.serial_state = "SERIAL_IDLE"

    def analog_statemachine(self):
        pass

    def traffic_statemachine(self):
        oldstate = self.traffic_state
        if self.traffic_state == "TRAFFIC_TEST_RED":
            self.red = 1
            self.yellow = 0
            self.green = 0
            if self.pulse > 1 * self.second:
                self.pulse = 0
                self.traffic_state = "TRAFFIC_TEST_RED_YELLOW"
        elif self.traffic_state == "TRAFFIC_TEST_RED_YELLOW":
            self.red = 1
            self.yellow = 1
            self.green = 0
            if self.pulse > 1 * self.second:
                self.pulse = 0
                self.traffic_state = "TRAFFIC_TEST_RED_YELLOW_GREEN"
        elif self.traffic_state == "TRAFFIC_TEST_RED_YELLOW_GREEN":
            self.red = 1
            self.yellow = 1
            self.green = 1
            if self.pulse > 1 * self.second:
                self.pulse = 0
                self.traffic_state = "TRAFFIC_RED"
        elif self.traffic_state == "TRAFFIC_GREEN":
            self.red = 0
            self.yellow = 0
            self.green = 1
            if self.request_green == 0:
                self.pulse = 0
                self.traffic_state = "TRAFFIC_YELLOW"
            if self.request_temp_error:
                self.traffic_state = "TRAFFIC_TEMP_ERROR"
        elif self.traffic_state == "TRAFFIC_YELLOW":
            self.red = 0
            self.yellow = 1
            self.green = 0
            if self.pulse > 4 * self.second:
                self.traffic_state = "TRAFFIC_RED"
        elif self.traffic_state == "TRAFFIC_RED":
            self.red = 1
            self.yellow = 0
            self.green = 0
            if self.request_green:
                self.traffic_state = "TRAFFIC_RED_YELLOW"
        elif self.traffic_state == "TRAFFIC_RED_YELLOW":
            self.red = 1
            self.yellow = 1
            self.green = 0
            if self.pulse > 4 * self.second:
                if self.request_temp_error:
                    self.traffic_state = "TRAFFIC_TEMP_ERROR"
                else:
                    self.traffic_state = "TRAFFIC_GREEN"
            if self.request_green == 0:
                self.traffic_state = "TRAFFIC_RED"
        elif self.traffic_state == "TRAFFIC_TEMP_ERROR":
            self.red = 0
            self.green = 0
            self.yellow = 1
            if self.pulse > 1 * self.second:
                self.pulse = 0
                self.traffic_state = "TRAFFIC_TEMP_ERROR_DARK"
            if not self.request_temp_error:
                if self.request_green:
                    self.traffic_state = "TRAFFIC_GREEN"
                else:
                    self.traffic_state = "TRAFFIC_RED"
        elif self.traffic_state == "TRAFFIC_TEMP_ERROR_DARK":
            self.red = 0
            self.green = 0
            self.yellow = 0
            if self.pulse > 1 * self.second:
                self.pulse = 0
                self.traffic_state = "TRAFFIC_TEMP_ERROR"
        elif self.traffic_state == "TRAFFIC_FAIL":
            self.red = 0
            self.green = 0
            if self.pulse > 2 * self.second:
                self.yellow = self.yellow ^ 1
                self.pulse = 0

        if oldstate != self.traffic_state:
            self.analog_cycles = 0
            self.pulse = 0

        if self.analog_cycles > 1:
            self.analog_cycles = 0
            self.error_state = self.check_plausible()
            if self.error_state != 0:
                self.traffic_state = "TRAFFIC_FAIL"

    def check_plausible(self):
        self.emulate_hardware()
        if self.green and self.sense["green"] < 500:
            return 1
        if self.red and self.sense["red"] < 500:
            return 1
        if self.yellow and self.sense["yellow"] < 500:
            return 1
        return 0

    def is_on(self, color):
        self.emulate_hardware()
        return self.sense[color] > 500

    def fail_bulb(self, name):
        if name not in self.bulb_resistance:
            raise KeyError(name)
        self.bulb_resistance[name] = 1e6

    def unfail_bulb(self, name):
        if name not in self.bulb_resistance:
            raise KeyError(name)
        self.bulb_resistance[name] = 1

    def emulate_hardware(self):
        self.batt_voltage -= self.discarge_rate
        tmp = {}
        for name, state in zip(
            ["red", "yellow", "green"], [self.red, self.yellow, self.green]
        ):
            # Calculate current in mA
            tmp[name] = 1000 * state / self.bulb_resistance[name]
        self.sense = tmp

    def switch_on(self):
        self.enable = True

    def switch_off(self):
        self.enable = False

    def shutdown(self):
        self._shutdown = True

    def main(self):
        while not self._shutdown:
            time.sleep(1 / self.second)
            if not self.enable:
                continue
            self.analog_cycles += 1
            self.pulse += 1
            self.traffic_statemachine()

            if self.ready:
                telegram = f"{STATE_MAP[self.traffic_state]} {self.batt_voltage} {self.error_state} {self.sense['red']} {self.sense['yellow']} {self.sense['green']}\r\n"

                os.write(self.pipe, telegram.encode("latin-1"))
