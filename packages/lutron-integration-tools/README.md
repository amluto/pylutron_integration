# pylutron-integration-cli

Command-line tools for [pylutron-integration](https://github.com/amluto/pylutron_integration).

## Installation

```bash
pip install pylutron-integration-cli
```

## Usage

### lutron_monitor

Monitor unsolicited device updates from a Lutron QSE-CI-NWK-E hub:

```bash
lutron_monitor [-u USERNAME] IP_ADDRESS
```

Examples:
```bash
lutron_monitor 192.168.1.100
lutron_monitor -u admin 192.168.1.100
```

You will be prompted for a password.
