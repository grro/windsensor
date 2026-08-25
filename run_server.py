import sys
import logging
from webthing import (SingleThing, WebThingServer)
from eltako import EltakoWsSensor
from eltako_mcp import EltakoMCPServer
from eltako_webthing import EltakoWsSensorThing


def run_server(port: int, chip_name: str, gpio_number: int):
    sensor = EltakoWsSensor(gpio_number=gpio_number, chip_name=chip_name)
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
        logging.getLogger("mcp.server.lowlevel").setLevel(logging.WARNING)
        port = int(sys.argv[1])
        chip_name = sys.argv[2] if len(sys.argv) > 3 else 'gpiochip0'
        gpio_number = int(sys.argv[3]) if len(sys.argv) > 3 else int(sys.argv[2])
        run_server(port, chip_name, gpio_number)
    except Exception as e:
        logging.error(str(e))
        raise e
