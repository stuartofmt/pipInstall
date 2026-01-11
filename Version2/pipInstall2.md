# Python package installer for DSF

A python script to install python package dependencies for DSF plugins.

Creates a Virtual Python Environment

Reports success on built-in modules.

Provides logic to (hopefully) avoid version conflicts due to different plugin requirements by installing specified versions.

Uses the default pip version for the OS.

Useage:
Usage pipInstall -m `<manifesr name>` -p `< plugin path >`

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
        3. If module is installed and no version given ==> try to install latest version
        4. If module is installed and version is given, try to honor request.
           Note: downgrades of version are attempted if requested.

Note: If a module is already installed but failes reinstall / update
      The occurence is logged and the install request is considered successful.

Logging is sent to journalctl with various messages indicating what was actually done.
Logging is also sent to a logfile pipInstall2.log

A special, dummy module "--verbose" can be included in

as the VERY FIRST module.  This enables verbose logging (see verbose_test.json)

Return Codes:

0 - All modules successfully installed or sensibly handled.

1 = Something nasty happened or one or more modules failed to install.
Usually this will be due to one of the following:
- No module was found for the requested version.
- pip could not handle the request.

#  Note: python scripts in Duet3d plugins need to have a shebang
 
#!/opt/dsf/plugins/`<plugin name>`/venv/bin/python -u  

## Tested in the following DSF environment
DSF 3.5.0x 3.6.x

Installed as:

/opt/dsf/bin/pipInstall2.py

with

sudo chmod 744 /opt/dsf/bin/pipInstall2.py

sudo chown dsf:dsf /opt/dsf/bin/pipInstall2.py

The following entry is expected in `/opt/dfs/conf/plugins.json`

  ```
  "InstallPythonPackageCommand": "/opt/dsf/bin/pipInstall2.py",
  ```
