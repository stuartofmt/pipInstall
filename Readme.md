# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

> [!WARNING]
> **`pipInstall.py` (Version 1) is no longer maintained.** It receives no fixes or updates. Use `pipInstall2.py` (Version 2).

There are two versions `pipInstall.py` and `pipInstall2.py`

`pipInstall.py` (no longer maintained) is compatible with previous versions of DWC where the installer is called on a per- module basis and installation is to the default system python.  This approach does not work with Debian Bookworm and likely, future releases of similar OS.

`pipInstall2.py` will be used from DWC 3.6.   It uses different calling parameters and is not backward compatible.  It creates a virtual environment for each plugin and iterates through all dependencies identified in the plugin manifest.

## Versions

Documentation for each version of pipInstall2 - usage, package descriptions, exit codes and change notes:

| pipInstall2 | For DWC / DSF | Documentation | Code |
| --- | --- | --- | --- |
| 2.4 | 3.7 | [docs/2.4](docs/2.4/README.md) - in development | [pipInstall2](https://github.com/stuartofmt/pipInstall/tree/pipInstall2) branch |
| 2.1 | 3.6 | [docs/2.1](docs/2.1/README.md) | Tag [v2.1.0](https://github.com/stuartofmt/pipInstall/tree/v2.1.0/Version2) |

pipInstall (Version 1, **no longer maintained**) is in the [pipInstall](https://github.com/stuartofmt/pipInstall/tree/pipInstall) branch, with its [documentation](https://github.com/stuartofmt/pipInstall/blob/pipInstall/readme.md).
