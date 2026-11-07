import asyncio
import logging
import threading
from typing import Protocol, cast, Dict, Optional
from fastmcp import FastMCP
from pydantic import AnyUrl, TypeAdapter
from zeroconf import IPVersion, ServiceInfo, Zeroconf
import socket
from eltako import EltakoWsSensor


logger = logging.getLogger(__name__)


class MDNS:

    def __init__(self):
        self.registered: Dict[str, ServiceInfo] = dict()
        self.zc: Optional[Zeroconf] = None
        self.service_type = "_mcp._tcp.local."
        self.hostname = socket.gethostname()
        self.local_ip = self.__detect_local_ip()

    def __detect_local_ip(self) -> Optional[str]:
        # UDP connect sends no packets; it only selects the outgoing interface
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except OSError as e:
            logging.debug("mDNS: no default route available: %s", e)

        try:
            ip = socket.gethostbyname(self.hostname)
            if not ip.startswith("127."):
                return ip
        except OSError as e:
            logging.debug("mDNS: hostname lookup failed: %s", e)
        return None

    def register_mdns(self, name: str, port: int):
        if self.local_ip is None:
            logging.warning("mDNS: no local IPv4 address found, skipping registration")
            return
        try:
            if self.zc is None:
                self.zc = Zeroconf(ip_version=IPVersion.V4Only)
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

    def close(self):
        if self.zc is None:
            return
        try:
            for service_info in self.registered.values():
                logging.info("mDNS: Unregistering %s", service_info.name)
                self.zc.unregister_service(service_info)
        except Exception as e:
            logging.warning("mDNS: unregistering failed: %s", e)
        finally:
            self.registered.clear()
            self.zc.close()
            self.zc = None



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
        self.__server_task: Optional[asyncio.Task] = None
        self.__thread: Optional[threading.Thread] = None
        self.sensor.add_listener(self.__on_value_changed)


        @self.mcp.resource("sensor://windspeed")
        def get_current_windspeed() -> str:
            """Provides the absolute real-time wind speed entry point.

            When clients read this endpoint, their subscription channel is
            dynamically caught and registered to receive automatic server-side pushes.
            """
            try:
                req_ctx = self.low_level_server.request_context
                if req_ctx and req_ctx.session and req_ctx.session not in self.active_sessions:
                    # Dynamically append active channel handle to our observer pool
                    self.active_sessions.add(cast(ResourceUpdateSession, req_ctx.session))
                    logger.info("[Server] Client session registered for updates (Resource: %s).", self.name)
            except Exception as e:
                logger.debug("[Server] Could not extract session metadata: %s", e)

            return str(self.sensor.windspeed_kmh)

        
        @self.mcp.tool()
        def get_wind_status() -> str:
            """Returns historical wind speed averages compiled over multiple granular windows.

            Use this tool when evaluating broader meteorological trends, such as verifying
            if persistent wind gusts require retracting awnings or external blinds.
            """
            return (
                f"1min average: {self.sensor.windspeed_kmh_1min_granularity} km/h, "
                f"30s average: {self.sensor.windspeed_kmh_30sec_granularity} km/h, "
                f"10s average: {self.sensor.windspeed_kmh_10sec_granularity} km/h, "
                f"5s average: {self.sensor.windspeed_kmh_5sec_granularity} km/h, "
                f"Current speed: {self.sensor.windspeed_kmh} km/h"
            )


    def __on_value_changed(self):
        if self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._trigger_client_notification(), self.loop)
            except RuntimeError:
                # loop closed concurrently during shutdown
                pass


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
        await self.mcp.run_async(transport="sse", host=self.host, port=self.port, show_banner=False)


    def start(self):
        self.mdns.register_mdns(self.name, self.port)
        self.__server_task = self.loop.create_task(self.__run())
        self.__thread = threading.Thread(target=self.__run_loop, name="mcp-server", daemon=True)
        self.__thread.start()

    def __run_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.__server_task)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MCP Server failed")
        finally:
            try:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            finally:
                self.loop.close()

    def stop(self, timeout_sec: float = 5):
        self.mdns.close()
        if self.__server_task is not None and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.__server_task.cancel)
            except RuntimeError:
                pass
        if self.__thread is not None:
            self.__thread.join(timeout_sec)
            if self.__thread.is_alive():
                logger.warning("MCP Server did not stop within %s sec", timeout_sec)
        logging.info("MCP Server stopped")