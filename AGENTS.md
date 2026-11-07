# AGENTS.md

> AI agents: read this file in full before changing files or running commands.

## Project

Reads wind speed from an Eltako wind sensor via GPIO (libgpiod) and exposes it as a WebThing API
(`port`, default `9860`) and an MCP SSE server (`port + 2`, `/sse`, announced via mDNS).

Target: Docker on a **Raspberry Pi Zero 2 W** (64-bit, 512 MB RAM, SD card). Keep CPU, memory, disk
writes and startup work minimal. The service must start without internet access; mDNS is optional.

## Where things are

- `run_server.py` – entry point (`<port> <chip#offset>`), wires sensor, WebThing and MCP
- `eltako.py` – GPIO edge counting (gpiod v1 + v2), km/h, median buffers
- `eltako_webthing.py` – WebThing properties
- `eltako_mcp.py` – MCP server (`sensor://windspeed`, `get_wind_status`) and mDNS
- `Dockerfile` – env `port`, `addr` (e.g. `gpiochip0#25`)
- `.github/workflows/publish_to_dockerhub.yml` – git tag → multi-arch image `grro/windsensor`

## Workflow (spec first)

1. State intended behavior first: inputs, outputs, ports, failure cases (no network, no GPIO, shutdown).
2. Get agreement before changing interfaces (property/tool names, ports, env vars).
3. Make the smallest change, verify, update `README.md` for user-visible changes.

## Commands

No test suite; verify in the ARM64 container:

```sh
docker build --platform linux/arm64/v8 --tag windsensor:dev .
docker run --rm --platform linux/arm64/v8 windsensor:dev python -c "import run_server, eltako_webthing, eltako_mcp"
```

Test MCP without hardware using a fake sensor (`add_listener()`, `windspeed_kmh*`), also with `--network none`.
On the Pi, check memory with `sudo docker top windsensor -o pid,rss,args` (`docker stats` shows 0B).

## Conventions

- Use `logging`, not `print`.
- Threads: sensor in daemon threads, WebThing on Tornado IOLoop, MCP on its own asyncio loop; cross-thread calls only via thread-safe APIs.
- Dependencies are pinned exactly; upgrade one at a time. No `fastmcp` major upgrade without testing (uses internals).
- `CMD` must `exec` Python so it gets `SIGINT` on `docker stop`.

## Definition of done

- ARM64 build and import check pass; changed behavior is exercised.
- No new errors on start/stop (known: harmless `CancelledError` traceback when MCP stops).
- No unnecessary network, disk or memory overhead on the Pi.
- `README.md` updated if needed; no secrets committed.
