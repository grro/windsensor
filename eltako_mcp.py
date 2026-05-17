import asyncio
import logging
import threading
from typing import Protocol, Dict
from fastmcp import FastMCP
from pydantic import TypeAdapter, AnyUrl
from zeroconf import IPVersion, ServiceInfo, Zeroconf
import socket
from eltako import EltakoWsSensor


logger = logging.getLogger(__name__)


class MDNS:

    def __init__(self):
        self.registered: Dict[str, ServiceInfo] = dict()
        self.zc = Zeroconf(ip_version=IPVersion.V4Only)
        self.service_type = "_mcp._tcp.local."
        self.hostname = socket.gethostname()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            self.local_ip = s.getsockname()[0]
        finally:
            s.close()


    def register_mdns(self, name: str, port: int):
        try:
            service_name = f"{name}.{self.service_type}"
            service_info = ServiceInfo(
                type_= self.service_type,
                name=service_name,
                addresses=[socket.inet_aton(self.local_ip)],
                port=port,
                properties={
                    "version": "1.0",
                    "path": "/sse",
                    "server_type": "fastmcp"
                },
                server=f"{self.hostname}.local.",
            )

            logging.info(f"mDNS: Registering {service_name} at {self.local_ip}:{port}")
            self.zc.register_service(service_info)
            self.registered[name] = service_info
        except Exception as e:
            logging.error(f"mDNS Registration failed: {e}")

    def unregister_mdns(self, name: str):
        service_info = self.registered.get(name)
        if service_info is not None:
            logging.info("mDNS: Unregistering service...")
            self.zc.unregister_service(service_info)
            self.zc.close()



class ResourceUpdateSession(Protocol):
    async def send_resource_updated(self, uri) -> None:
        ...



class EltakoMCPServer:
    def __init__(self, port: int, sensor: EltakoWsSensor, name: str = "windsensor", host: str = "0.0.0.0"):
        self.name = name
        self.host = host
        self.port = port

        self.mdns = MDNS()
        self.mcp = FastMCP(self.name)
        self.active_sessions: set[ResourceUpdateSession] = set()
        self.low_level_server = self.mcp._mcp_server
        self.sensor = sensor
        self.loop = asyncio.new_event_loop()
        self.sensor.add_listener(self.__on_value_changed)


        @self.mcp.tool()
        def get_wind_status() -> str:
            """
            Returns the current wind speed data for various time intervals.
            """

            status = (
                f"1min average: {self.sensor.windspeed_kmh_1min_granularity} km/h, "
                f"30s average: {self.sensor.windspeed_kmh_30sec_granularity} km/h, "
                f"10s average: {self.sensor.windspeed_kmh_10sec_granularity} km/h, "
                f"5s average: {self.sensor.windspeed_kmh_5sec_granularity} km/h, "
                f"Current speed: {self.sensor.windspeed_kmh} km/h"
            )
            return status


    def __on_value_changed(self):
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._trigger_client_notification(), self.loop)


    async def _trigger_client_notification(self) -> None:
        if not self.active_sessions:
            return

        dead_sessions = set()
        for session in self.active_sessions:
            try:
                await session.send_resource_updated(TypeAdapter(AnyUrl).validate_python("sensor://windspeed"))
            except Exception as e:
                logger.warning("[Server] Client not reachable: %s", e)
                dead_sessions.add(session)

        self.active_sessions.difference_update(dead_sessions)

    async def __run(self) -> None:
        logger.info(f"MCP Server '{self.name}' running on http://{self.host}:{self.port}/sse")
        await self.mcp.run_async(transport="sse", host=self.host, port=self.port)


    def start(self):
        self.mdns.register_mdns(self.name, self.port)

        def _run_loop():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self.__run())
            finally:
                self.loop.close()

        thread = threading.Thread(target=_run_loop, daemon=True)
        thread.start()


    def stop(self):
        self.mdns.unregister_mdns(self.name)
        self.loop.stop()
        logging.info("MCP Server stopped")