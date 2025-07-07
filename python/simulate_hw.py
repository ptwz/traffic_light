import os
import threading
import time
import pty


class SimBase:
    def __init__(self):
        """
        Initializes a simulator.

        Brings up the pts, sets self.pts with is the path of the pts to be used
        by clients and sets up the pipe.
        Also starts up a thread for handling input from clients.
        """
        self.pts, self.pipe = self._get_pts()
        self._task = threading.Thread(target=self.reader_task, daemon=True)
        self._task.start()

    def _get_pts(self):
        """
        Allocates a pts device, enable its io and return both the name
        of the newly opened pts and the pipe for own use
        """
        (master, slave) = pty.openpty()
        slave_pts = os.ttyname(slave)
        return (slave_pts, master)

    def reader_task(self):
        while True:
            line = os.read(self.pipe, 1)
            print("got ", line)
            self.process(line)

    def process(self, line):
        pass


class SimController(SimBase):
    def process(self, line):
        print(line.strip().split(" "))

    def press_green(self):
        self.pipe.write(b"G")

    def press_red(self):
        self.pipe.write(b"g")


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
        self.pulse = 0
        self.analog_cycles = 0
        self.error_state = 0

    def process(self, line):
        """Emulate the "serial_statemachine" for the JAL-Firmware"""
        for tmp in line.strip():
            if self.serial_state == "SERIAL_IDLE":
                if tmp == b"G":
                    self.request_green = True
                if tmp == b"g":
                    self.request_green = False
                if tmp == b"e":
                    self.request_temp_error = True
                if tmp == b"E":
                    self.request_temp_error = False
                if ((tmp == b"\r") | (tmp == b"\n")) & (
                    self.serial_state == "SERIAL_READ_DATA"
                ):
                    self.serial_state = "SERIAL_IDLE"
                if tmp == 27:
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
        elif self.traffic_statemachine == "TRAFFIC_FAIL":
            self.red = 0
            self.green = 0
            if self.pulse > 2 * self.second:
                self.yellow = not self.yellow
                self.pulse = 0

        if oldstate != self.traffic_state:
            self.analog_cycles = 0
            self.pulse = 0

        if self.analog_cycles > 10:
            self.analog_cycles = 0
            self.error_state = self.check_plausible()
            if self.error_state != 0:
                self.traffic_state = "TRAFFIC_FAIL"

    def check_plausible(self):
        # TODO Implement me!
        return 0

    def emulate_hardware(self):
        self.batt_voltage -= self.discarge_rate
        tmp = {}
        for name, state in zip(
            ["red", "yellow", "green"], [self.red, self.yellow, self.green]
        ):
            # Calculate current in mA
            tmp[name] = 1000 * state / self.bulb_resistance[name]
        self.sense = tmp

    def main(self):
        while True:
            time.sleep(1 / self.second)
            self.analog_cycles += 1
            self.pulse += 1
            self.traffic_statemachine()
            self.emulate_hardware()

            telegram = f"{self.traffic_state} {self.batt_voltage} {self.error_state} {self.sense['red']} {self.sense['yellow']} {self.sense['green']}\r\n"

            os.write(self.pipe, telegram.encode("latin-1"))


x = SimLight()
print(x.pts)
x.main()
