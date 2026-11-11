# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

> [!WARNING]
> **`pipInstall.py` (Version 1) is no longer maintained.** It receives no fixes or updates. Use `pipInstall2.py` (Version 2).

There are two versions `pipInstall.py` and `pipInstall2.py`

`pipInstall.py` (no longer maintained) is compatible with previous versions of DWC where the installer is called on a per- module basis and installation is to the default system python.  This approach does not work with Debian Bookworm and likely, future releases of similar OS.

`pipInstall2.py` will be used from DWC 3.6.   It uses different calling parameters and is not backward compatible.  It creates a virtual environment for each plugin and iterates through all dependencies identified in the plugin manifest.

## Branches

Each version is kept on its own branch:

| Branch | Contents |
| --- | --- |
| [pipInstall](https://github.com/stuartofmt/pipInstall/tree/pipInstall) | Version 1 (**no longer maintained**) - [documentation](https://github.com/stuartofmt/pipInstall/blob/pipInstall/readme.md), [script](https://github.com/stuartofmt/pipInstall/blob/pipInstall/pipInstall.py) |
| [pipInstall2](https://github.com/stuartofmt/pipInstall/tree/pipInstall2) | Version 2 - [documentation](https://github.com/stuartofmt/pipInstall/blob/pipInstall2/readme.md), [script](https://github.com/stuartofmt/pipInstall/blob/pipInstall2/pipInstall2.py), [release notes](https://github.com/stuartofmt/pipInstall/blob/pipInstall2/release-notes.md) |
| master | This Readme only |
