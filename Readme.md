# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

Creates a Virtual Python Environment if < plugin name > is provided

Reports success on built-in modules.

Provides logic to (hopefully) avoid version conflicts due to different plugin requirements by installing specified versions.

Uses the default pip version for the OS.

Useage:
Usage pipInstall `<module name>` `< plugin name >`

Expects a single module name with or without a version number.

If version number is supplied it must use one of the following comparisons:
```
==
>=
<=
>
<
~=    Note ~= will be converted to >=
```

Version numbers specifying max / min ranges are not supported

Rules (executed in order):
Try to install unless:
    In all cases:
        1. If the module is a Built-In ==> do nothing
    If installing into the default OS environment
        2. If the module is not installed ==> try to Install
        3. If module is installed and no version given ==> do nothing
           prevents accidental breaking of another plugin
           can be over-ridden by supplying version info
        4. If installed version >= requested version ==> do nothing

Note: If a module is already installed but failes reinstall / update
      The occurence is logged and the install request is considered successful.

Logging is sent to journalctl with various messages indicating what was actually done.

Return Codes:

0 - Successfully installed or already installed.  Log provides details.

1 = Something nasty happened or one of the following:

No module was specified.

Only one module can be specified.

Unsupported Conditional.

pip could not handle the request.

## Tested in the following DSF environment using DSF 3.5.0x

Installed as:

/opt/dsf/bin/pipIinstall.py

with

sudo chmod 744 /opt/dsf/bin/pipInstall.py

sudo chown dsf:dsf /opt/dsf/bin/pipInstall.py

The following entry are expected in `/opt/dfs/conf/plugins.json`

  ```
  "InstallPythonPackageCommand": "/opt/dsf/bin/pipInstall.py",
  ```
