# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

There are two versions `pipInstall.py` and `pipInstall2.py`

`pipInstall.py` is compatable with previous versions of DWC where the installer is called on a per- module basis and installation is to the default system python.  This approach does not work with Debian Bookworm and likely, furure releases of similar OS.

`pipInstall2.py` will be used from DWC 3.6.   It uses different calling parameters and is not backward compatible.  It creates a virtual environment for each plugin and iterates through all dependencies identified in the plugin manifest.