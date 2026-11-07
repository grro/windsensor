import os
import sys
import logging
from webthing import (SingleThing, WebThingServer)
from eltako import EltakoWsSensor
from eltako_mcp import EltakoMCPServer
from eltako_webthing import EltakoWsSensorThing


def run_server(port: int, chip_name: str, gpio_number: int):
    sensor = EltakoWsSensor(gpio_number=gpio_number, chip_name=chip_name)
    mcp_server = None
    webthing_server = None
    try:
        mcp_server = EltakoMCPServer(port+2, sensor)
        webthing_server = WebThingServer(SingleThing(EltakoWsSensorThing(sensor)), port=port, disable_host_validation=True)
        mcp_server.start()
        logging.info('starting the server')
        webthing_server.start()
    except KeyboardInterrupt:
        logging.info('stopping the server')
    finally:
        if webthing_server is not None:
            _stop_webthing(webthing_server)
        if mcp_server is not None:
            mcp_server.stop()
        sensor.close()
        logging.info('done')


def _stop_webthing(webthing_server: WebThingServer):
    # stop() fails if start() aborted before the zeroconf registration
    try:
        if hasattr(webthing_server, 'zeroconf'):
            webthing_server.stop()
        else:
            webthing_server.server.stop()
    except Exception as e:
        logging.warning('stopping the webthing server failed: %s', e)


def parse_gpio_args(args, chip_default: str = 'gpiochip0'):
    # Supports:
    #   "gpiochip0#11" (combined chip#offset)
    #   "gpiochip0" "11" (separate chip and offset)
    #   "11" (bare offset, uses chip_default)
    if len(args) == 1:
        spec = args[0]
        if '#' in spec:
            chip_name, offset = spec.split('#', 1)
            return chip_name, int(offset)
        return chip_default, int(spec)
    return args[0], int(args[1])


if __name__ == '__main__':
    try:
        logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger('tornado.access').setLevel(logging.ERROR)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
        logging.getLogger('starlette.middleware.base').setLevel(logging.WARNING)
        logging.getLogger('fastmcp').setLevel(logging.WARNING)
        logging.getLogger('mcp').setLevel(logging.WARNING)
        logging.getLogger('mcp.server').setLevel(logging.WARNING)
        logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.WARNING)
        logging.getLogger('uvicorn.access').disabled = True
        logging.getLogger('uvicorn.error').setLevel(logging.WARNING)
        logging.getLogger('uvicorn').setLevel(logging.WARNING)
        logging.info('windsensor version %s', os.environ.get('WINDSENSOR_VERSION', 'dev'))
        port = int(sys.argv[1])
        chip_name, gpio_number = parse_gpio_args(sys.argv[2:])
        run_server(port, chip_name, gpio_number)
    except Exception as e:
        logging.error(str(e))
        raise e
