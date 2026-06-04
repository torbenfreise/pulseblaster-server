# SpinCore PulseBlaster Service

Implementation of a gRPC service for the SpinCore PulseBlaster intended for use with h2pcontrol.

This service should be run on a device connected to a SpinCore PulseBlaster, and enables
remote programming via gRPC.

Configure the address where the service listens in the [config.toml](config.toml) file.

This project has been adapted from the [h2pcontrol-server-template](https://github.com/torbenfreise/h2pcontrol-server-template)

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [spinapi](https://www.spincore.com/support/spinapi/)

## Quick Start

```bash
uv run src/main.py
```

## Usage

Consult the [h2pcontrol Buf Schema Registry](https://buf.build/beyer-labs/h2pcontrol) to see the procedures implemented by this service.
