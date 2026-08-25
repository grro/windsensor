import RPi.GPIO as GPIO
import logging
import time
from threading import Thread
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

    def __init__(self, gpio_number: int):
        logging.info("listening on GPIO " + str(gpio_number))
        self.gpio_number = gpio_number
        self.__listeners = set()
        self.start_time = time.time()
        self.num_raise_events = 0
        self.windspeed_kmh = 0
        self.__measure_period_sec = 2
        self.__5sec_buffer= RingBuffer(round(5/self.__measure_period_sec))
        self.__10sec_buffer= RingBuffer(round(10/self.__measure_period_sec))
        self.__30sec_buffer= RingBuffer(round(30/self.__measure_period_sec))
        self.__1min_buffer= RingBuffer(round(60/self.__measure_period_sec))
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.gpio_number, GPIO.IN)
        GPIO.add_event_detect(self.gpio_number, GPIO.RISING, callback=self.__spin, bouncetime=5)
        Thread(target=self.__measure_loop, daemon=True).start()


    def add_listener(self, listener):
        self.__listeners.add(listener)

    def __notify_listener(self):
        for listener in self.__listeners:
            listener()

    def __spin(self, channel):
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
            elapsed_sec = time.time() - self.start_time
            return self.__compute_speed_kmh(self.num_raise_events, elapsed_sec)
        except Exception as e:
            logging.error(e)
            return 0
        finally:
            self.num_raise_events = 0
            self.start_time = time.time()

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