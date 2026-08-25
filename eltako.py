import logging
import time
import importlib
from datetime import timedelta
from threading import Lock, Thread
from time import sleep


class RingBuffer:

    def __init__(self, size: int):
        self.buffer =  [5] * size
        self.pos = 0

    def add(self, value: int):
        if self.pos >= len(self.buffer):
            self.pos = 0
        self.buffer[self.pos] = value
        self.pos += 1

    @property
    def median(self) -> int:
        values = sorted(list(self.buffer))
        return values[round(len(values) * 0.5)]



class EltakoWsSensor:

    def __init__(self, chip_name: str,  gpio_number: int):
        logging.info("listening on GPIO line offset " + str(gpio_number) + " on " + chip_name)
        self.gpio_number = gpio_number
        self.chip_name = chip_name
        self.__gpiod = self.__load_gpiod()
        self.__listeners = set()
        self.start_time = time.monotonic()
        self.num_raise_events = 0
        self.windspeed_kmh = 0
        self.__debounce_sec = 0.005
        self.__last_spin_time = 0.0
        self.__counter_lock = Lock()
        self.__measure_period_sec = 2
        self.__5sec_buffer= RingBuffer(round(5/self.__measure_period_sec))
        self.__10sec_buffer= RingBuffer(round(10/self.__measure_period_sec))
        self.__30sec_buffer= RingBuffer(round(30/self.__measure_period_sec))
        self.__1min_buffer= RingBuffer(round(60/self.__measure_period_sec))

        self.__gpiod_backend = None
        self.__chip = None
        self.__line = None
        self.__line_request = None
        self.__setup_gpio()

        Thread(target=self.__edge_loop, daemon=True).start()
        Thread(target=self.__measure_loop, daemon=True).start()

    def __load_gpiod(self):
        try:
            return importlib.import_module("gpiod")
        except ModuleNotFoundError as error:
            raise RuntimeError("Missing dependency 'gpiod'. Install requirements.txt to enable GPIO access.") from error

    def __setup_gpio(self):
        try:
            self.__setup_gpio_v1()
            self.__gpiod_backend = "v1"
            return
        except Exception:
            logging.debug("gpiod v1 API not available, trying v2 API", exc_info=True)

        self.__setup_gpio_v2()
        self.__gpiod_backend = "v2"

    def __setup_gpio_v1(self):
        self.__chip = self.__gpiod.Chip(self.chip_name)
        self.__line = self.__chip.get_line(self.gpio_number)
        self.__line.request(consumer="eltako-ws-sensor", type=self.__gpiod.LINE_REQ_EV_RISING_EDGE)

    def __setup_gpio_v2(self):
        chip_path = self.chip_name if self.chip_name.startswith("/dev/") else f"/dev/{self.chip_name}"
        line_settings = self.__gpiod.LineSettings()

        if hasattr(self.__gpiod, "line") and hasattr(self.__gpiod.line, "Direction"):
            line_settings.direction = self.__gpiod.line.Direction.INPUT
        if hasattr(self.__gpiod, "line") and hasattr(self.__gpiod.line, "Edge"):
            line_settings.edge_detection = self.__gpiod.line.Edge.RISING
        if hasattr(line_settings, "debounce_period"):
            line_settings.debounce_period = timedelta(milliseconds=5)

        self.__line_request = self.__gpiod.request_lines(
            chip_path,
            consumer="eltako-ws-sensor",
            config={self.gpio_number: line_settings},
        )


    def add_listener(self, listener):
        self.__listeners.add(listener)

    def __notify_listener(self):
        for listener in self.__listeners:
            listener()

    def __edge_loop(self):
        while True:
            try:
                if self.__gpiod_backend == "v1":
                    if self.__wait_for_event_v1():
                        self.__line.event_read()
                        self.__spin()
                else:
                    for _ in self.__read_edge_events_v2():
                        self.__spin()
            except Exception as e:
                logging.error("edge loop failed: %s", str(e))
                sleep(0.2)

    def __wait_for_event_v1(self) -> bool:
        try:
            return self.__line.event_wait(sec=1)
        except TypeError:
            return self.__line.event_wait(timeout=1)

    def __read_edge_events_v2(self):
        if hasattr(self.__line_request, "read_edge_events"):
            try:
                events = self.__line_request.read_edge_events(timeout=timedelta(seconds=1))
            except TypeError:
                events = self.__line_request.read_edge_events(timeout=1)
            return events or []

        if hasattr(self.__line_request, "wait_edge_events") and self.__line_request.wait_edge_events(timeout=timedelta(seconds=1)):
            return self.__line_request.read_edge_events() or []

        return []

    def __spin(self):
        now = time.monotonic()
        if now - self.__last_spin_time < self.__debounce_sec:
            return

        self.__last_spin_time = now
        with self.__counter_lock:
            self.num_raise_events = self.num_raise_events + 1

    def __compute_speed_kmh(self, num_raise_events, elapsed_sec) -> int:
        if num_raise_events == 0 or elapsed_sec == 0:
            return 0
        else:
            rotation_per_sec = num_raise_events / elapsed_sec
            lowspeed_factor = 1.761
            highspeed_factor = 3.013
            km_per_hour = lowspeed_factor / (1 + rotation_per_sec) + highspeed_factor * rotation_per_sec
            if km_per_hour < 2:
                km_per_hour = 0
            return int(round(km_per_hour, 0))

    def __measure(self) -> int:
        try:
            elapsed_sec = time.monotonic() - self.start_time
            with self.__counter_lock:
                num_raise_events = self.num_raise_events
                self.num_raise_events = 0
                self.start_time = time.monotonic()
            return self.__compute_speed_kmh(num_raise_events, elapsed_sec)
        except Exception as e:
            logging.error(e)
            return 0

    def close(self):
        try:
            if self.__line_request is not None and hasattr(self.__line_request, "release"):
                self.__line_request.release()
        except Exception:
            logging.debug("releasing gpiod line request failed", exc_info=True)

        try:
            if self.__line is not None and hasattr(self.__line, "release"):
                self.__line.release()
        except Exception:
            logging.debug("releasing gpiod line failed", exc_info=True)

        try:
            if self.__chip is not None and hasattr(self.__chip, "close"):
                self.__chip.close()
        except Exception:
            logging.debug("closing gpiod chip failed", exc_info=True)

    def __measure_loop(self):
        while True:
            try:
                self.windspeed_kmh = self.__measure()
                self.__5sec_buffer.add(self.windspeed_kmh)
                self.__10sec_buffer.add(self.windspeed_kmh)
                self.__30sec_buffer.add(self.windspeed_kmh)
                self.__1min_buffer.add(self.windspeed_kmh)
                self.__notify_listener()
            except Exception as e:
                logging.error(str(e))
            sleep(self.__measure_period_sec)

    @property
    def windspeed_kmh_10sec_granularity(self) -> int:
        return self.__10sec_buffer.median

    @property
    def windspeed_kmh_5sec_granularity(self) -> int:
        return self.__5sec_buffer.median

    @property
    def windspeed_kmh_30sec_granularity(self) -> int:
        return self.__30sec_buffer.median

    @property
    def windspeed_kmh_1min_granularity(self) -> int:
        return self.__1min_buffer.median