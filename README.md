# Windsensor

Read wind speed from an [Eltako wind sensor](https://www.eltako.com/fileadmin/downloads/en/_datasheets/Datasheet_WS.pdf) on a Raspberry Pi and expose the measurements through:
- a **WebThing HTTP API**
- an **MCP server** over **SSE**

This project is designed for **Raspberry Pi / Linux GPIO environments**. The sensor is connected to a GPIO line
and measured continuously in the background.

## Features

- Reads pulses from an Eltako reed-switch wind sensor
- Calculates current wind speed in **km/h**
- Publishes smoothed values for:
  - current value
  - 5-second median
  - 10-second median
  - 30-second median
  - 1-minute median
- Exposes the values through a WebThing-compatible HTTP endpoint
- Starts an MCP server on a second port for real-time push updates 

## Requirements

### Hardware

- Raspberry Pi with accessible GPIO
- Eltako wind sensor wired to a GPIO input pin

For wiring background and hardware examples, see
- [Measure Wind Speed with Eltako Windsensor and Win10 IoT Core](https://www.hackster.io/daniel-kreuzhofer/measure-wind-speed-with-eltako-windsensor-and-win10-iot-core-e1e42a)

### Software

- Python 3.x
- Linux / Raspberry Pi OS recommended
- Access to `/dev/gpiochip*` (libgpiod)

### GPIO numbering

- The second CLI argument is the **GPIO line offset** (libgpiod), not `RPi.GPIO` BOARD numbering.
- Example for BCM17 on `gpiochip0`: line offset `17`.
