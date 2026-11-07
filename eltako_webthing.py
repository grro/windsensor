import tornado.ioloop
from webthing import (Property, Thing, Value)
from eltako import EltakoWsSensor



class EltakoWsSensorThing(Thing):

    # regarding capabilities refer https://iot.mozilla.org/schemas
    # there is also another schema registry http://iotschema.org/docs/full.html not used by webthing

    def __init__(self, sensor: EltakoWsSensor):
        Thing.__init__(
            self,
            'urn:dev:ops:eltakowsSensor-1',
            'Wind Sensor',
            ['MultiLevelSensor'],
            "wind sensor"
        )

        self.sensor = sensor
        self.sensor.add_listener(self.on_value_changed)
        self.ioloop = tornado.ioloop.IOLoop.current()

        self.windspeed = Value(self.sensor.windspeed_kmh)
        self.add_property(
            Property(self,
                     'windspeed',
                     self.windspeed,
                     metadata={
                         'title': 'Windspeed',
                         'type': 'number',
                         'description': 'The current windspeed',
                         'unit': 'km/h',
                         'readOnly': True,
                     }))

        self.windspeed_5sec = Value(self.sensor.windspeed_kmh_5sec_granularity)
        self.add_property(
            Property(self,
                     'windspeed_5sec',
                     self.windspeed_5sec,
                     metadata={
                         'title': 'windspeed_5sec',
                         'type': 'number',
                         'description': 'The current windspeed smoothen 5sec',
                         'unit': 'km/h',
                         'readOnly': True,
                     }))

        self.windspeed_10sec = Value(self.sensor.windspeed_kmh_10sec_granularity)
        self.add_property(
            Property(self,
                     'windspeed_10sec',
                     self.windspeed_10sec,
                     metadata={
                         'title': 'windspeed_10sec',
                         'type': 'number',
                         'description': 'The current windspeed smoothen 10sec',
                         'unit': 'km/h',
                         'readOnly': True,
                     }))

        self.windspeed_30sec = Value(self.sensor.windspeed_kmh_30sec_granularity)
        self.add_property(
            Property(self,
                     'windspeed_30sec',
                     self.windspeed_30sec,
                     metadata={
                         'title': 'windspeed_30sec',
                         'type': 'number',
                         'description': 'The current windspeed smoothen 30sec',
                         'unit': 'km/h',
                         'readOnly': True,
                     }))

        self.windspeed_1min = Value(self.sensor.windspeed_kmh_1min_granularity)
        self.add_property(
            Property(self,
                     'windspeed_1min',
                     self.windspeed_1min,
                     metadata={
                         'title': 'windspeed_1min',
                         'type': 'number',
                         'description': 'The current windspeed smoothen 1min',
                         'unit': 'km/h',
                         'readOnly': True,
                     }))

    def on_value_changed(self):
        self.ioloop.add_callback(self.__on_value_changed)

    def __on_value_changed(self):
        self.windspeed.notify_of_external_update(self.sensor.windspeed_kmh)
        self.windspeed_5sec.notify_of_external_update(self.sensor.windspeed_kmh_5sec_granularity)
        self.windspeed_10sec.notify_of_external_update(self.sensor.windspeed_kmh_10sec_granularity)
        self.windspeed_30sec.notify_of_external_update(self.sensor.windspeed_kmh_30sec_granularity)
        self.windspeed_1min.notify_of_external_update(self.sensor.windspeed_kmh_1min_granularity)
