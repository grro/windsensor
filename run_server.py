import sys
import logging
from webthing import (SingleThing, WebThingServer)
from eltako import EltakoWsSensor
from eltako_mcp import EltakoMCPServer
from eltako_webthing import EltakoWsSensorThing


def run_server(port: int, chip_name: str, gpio_number: int):
    sensor = EltakoWsSensor(chip_name, gpio_number)
    mcp_server = EltakoMCPServer(port+2, sensor)
    webthing_server = WebThingServer(SingleThing(EltakoWsSensorThing(sensor)), port=port, disable_host_validation=True)

    try:
        mcp_server.start()
        logging.info('starting the server')
        webthing_server.start()
    except KeyboardInterrupt:
        logging.info('stopping the server')
        mcp_server.stop()
        webthing_server.stop()
        logging.info('done')
    finally:
        sensor.close()


if __name__ == '__main__':
    try:
        logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger('tornado.access').setLevel(logging.ERROR)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
        run_server(int(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
    except Exception as e:
        logging.error(str(e))
        raise e
