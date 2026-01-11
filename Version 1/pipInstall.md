# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

Reports success on built-in modules.

Provides logic to (hopefully) avoid version conflicts due to different plugin requirements by installing specified versions.

Uses the default pip version for the OS.

Useage:
Usage pipInstall `<module name>`

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
        1. If the module is a Built-In ==> do nothing
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

#  Note: python scripts in Duet3d plugins need to have a shebang
 
#!/usr/bin/python -u  

## Tested in the following DSF environment
3.5.x

Installed as:

/opt/dsf/bin/pipIinstall.py

with

sudo chmod 744 /opt/dsf/bin/pipInstall.py

sudo chown dsf:dsf /opt/dsf/bin/pipInstall.py

The following entry is expected in `/opt/dfs/conf/plugins.json`

  ```
  "InstallPythonPackageCommand": "/opt/dsf/bin/pipInstall.py",
  ```
