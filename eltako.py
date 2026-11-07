import logging
import math
import time
import importlib
from collections import deque
from datetime import timedelta
from threading import Event, Lock, Thread


class RingBuffer:

    def __init__(self, size: int):
        self.__values = deque(maxlen=size)
        self.__lock = Lock()

    def add(self, value: int):
        with self.__lock:
            self.__values.append(value)

    @property
    def median(self) -> int:
        with self.__lock:
            values = sorted(self.__values)
        if not values:
            return 0
        mid = len(values) // 2
        if len(values) % 2 == 1:
            return values[mid]
        # round half up; values are non-negative
        return int((values[mid - 1] + values[mid]) / 2 + 0.5)



class EltakoWsSensor:

    def __init__(self, chip_name: str,  gpio_number: int):
        logging.info("listening on GPIO  " + chip_name + "#" + str(gpio_number))
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
        self.__5sec_buffer = RingBuffer(self.__buffer_size(5))
        self.__10sec_buffer = RingBuffer(self.__buffer_size(10))
        self.__30sec_buffer = RingBuffer(self.__buffer_size(30))
        self.__1min_buffer = RingBuffer(self.__buffer_size(60))

        self.__gpiod_backend = None
        self.__chip = None
        self.__line = None
        self.__line_request = None
        self.__setup_gpio()

        self.__stopped = Event()
        self.__threads = [Thread(target=self.__edge_loop, name="gpio-edge", daemon=True),
                          Thread(target=self.__measure_loop, name="gpio-measure", daemon=True)]
        for thread in self.__threads:
            thread.start()

    def __buffer_size(self, window_sec: int) -> int:
        return max(1, math.ceil(window_sec / self.__measure_period_sec))

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
        while not self.__stopped.is_set():
            try:
                if self.__gpiod_backend == "v1":
                    if self.__wait_for_event_v1():
                        self.__line.event_read()
                        self.__spin()
                else:
                    for _ in self.__read_edge_events_v2():
                        self.__spin()
            except Exception as e:
                if self.__stopped.is_set():
                    break
                logging.error("edge loop failed: %s", str(e))
                self.__stopped.wait(0.2)

    def __wait_for_event_v1(self) -> bool:
        try:
            return self.__line.event_wait(sec=1)
        except TypeError:
            return self.__line.event_wait(timeout=1)

    def __read_edge_events_v2(self):
        if hasattr(self.__line_request, "wait_edge_events"):
            if not self.__wait_edge_events_v2():
                return []
            return self.__line_request.read_edge_events() or []

        # Fallback for bindings without wait_edge_events: blocking read
        return self.__line_request.read_edge_events() or []

    def __wait_edge_events_v2(self) -> bool:
        try:
            return self.__line_request.wait_edge_events(timedelta(seconds=1))
        except TypeError:
            return self.__line_request.wait_edge_events(1)

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

    def close(self, timeout_sec: float = 2):
        self.__stopped.set()
        for thread in self.__threads:
            thread.join(timeout_sec)
            if thread.is_alive():
                logging.warning("thread %s did not stop within %s sec", thread.name, timeout_sec)

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
        while not self.__stopped.wait(self.__measure_period_sec):
            try:
                self.windspeed_kmh = self.__measure()
                self.__5sec_buffer.add(self.windspeed_kmh)
                self.__10sec_buffer.add(self.windspeed_kmh)
                self.__30sec_buffer.add(self.windspeed_kmh)
                self.__1min_buffer.add(self.windspeed_kmh)
                self.__notify_listener()
            except Exception as e:
                logging.error(str(e))

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