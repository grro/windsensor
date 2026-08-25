import sys
import logging
import tornado.ioloop
from webthing import (SingleThing, Property, Thing, Value, WebThingServer)
from eltako import EltakoWsSensor
from eltako_mcp import EltakoMCPServer



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


def run_server(port: int, gpio_number: int):
    sensor = EltakoWsSensor(gpio_number)
    mcp_server = EltakoMCPServer(port+2, sensor)
    server = WebThingServer(SingleThing(EltakoWsSensorThing(sensor)), port=port, disable_host_validation=True)

    try:
        mcp_server.start()
        logging.info('starting the server')
        server.start()
    except KeyboardInterrupt:
        logging.info('stopping the server')
        mcp_server.stop()
        server.stop()
        logging.info('done')
    finally:
        sensor.close()


if __name__ == '__main__':
    try:
        logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger('tornado.access').setLevel(logging.ERROR)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
        run_server(int(sys.argv[1]), int(sys.argv[2]))
    except Exception as e:
        logging.error(str(e))
        raise e
