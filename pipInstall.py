#!/usr/bin/env python

"""
Install python modules and create a virtual environment for the plugin.

# Copyright (C) 2023 Stuart Strolin all rights reserved.
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT

Useage:
Usage pipInstall.py <module name> <plugin name>

Expects a single module name (with or without version number) and the plugin name

If <plugin name> is provided: A virtual environment will be created for the plugin at
pluginPath/<plugin name>/venv (see pluginPath below)

If <plugin name > is not provided: installation will be to the OS default environment.
This is NOT recommended but is included to provide backward compatibility

If version number is supplied it must use one of the following comparisons:
==
>=
<=
>
<
~=    Note ~= will be converted to >=

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
      The occurence is logged and the install request is considered successful        

Return Codes:

0 - Successfully installed or already installed.  Details are sent to journalctl
1 = Something nasty happened

Verson:
1.0.0
Initial Release
1.0.2
Added additional check to function pipinstalled.  Uses pip list because some modules do not show up in global list
2.0.0
Added support for virtual environments
 - separate rules for system env and venv
Added normalization of module names according to pip standard
Added better handling for installed modules that cannot be upgraded
Simplified return codes
Improved logging
"""
import subprocess
import sys
import logging
from pkg_resources import parse_version as version
import re
import os
import sysconfig

# Configuration Variables
pluginPath = '/opt/dsf/plugins'
pythonVersion = 'python'  #Possible future use with additional input of specific version

def createLogger(logname):   ##### Create a custom logger so messages go to journalctl#####
    global logger
    logger = logging.getLogger(logname)
    logger.propagate = False
    # Create handler for console output
    c_handler = logging.StreamHandler()
    c_format = logging.Formatter('%(message)s')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)
    logger.setLevel(logging.DEBUG)

def validateArguments():
    numArgs = len(sys.argv)
    if numArgs <= 1:
        logger.info('No module was specified: ' + str(sys.argv))
        sys.exit(1)
    elif numArgs == 2:
        # Need 3 arguments for externally managed environments
        EMFile = sysconfig.get_path("stdlib", sysconfig.get_default_scheme()) + '/EXTERNALLY-MANAGED'
        if os.path.isfile(EMFile):
            logger.info('OS does not allow install to System Python - Exiting')
            sys.exit(1)
        reqVersion = sys.argv[1]
        pName = ''
    elif numArgs == 3:
        reqVersion = sys.argv[1]
        pName  = sys.argv[2]
    elif numArgs > 3:
        logger.info('Too many arguments.' + str(sys.argv))
        sys.exit(1)
    return  reqVersion, pName

def parseVersion(request):
# Get the module name any conditional and version
    if ',' in request:
        logger.info('Unsupported Conditional in: ' + str(request))
        sys.exit(1)

    result = []
    conditionals = '|'.join(['==', '~=', '>=', '<=', '>', '<'])
    regex = '(.+)(' + conditionals + ')(.+)'
    result = re.findall(regex,request)

    if len(result) == 0: # No conditional
        result = [(request, '', '')]

    result = list(result[0]) # Convert tuple to list
    if result[1] == '~=':
        result [1] = '>='
    return result[0], result[1], result[2]

def runsubprocess(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=True)
        if result.returncode != 0:
            if str(result.stderr) != '' and '[Error]' in str(result.stderr):
                logger.info('Command Failure: ' + str(cmd))
                logger.debug('Error = ' + str(result.stderr))
                logger.debug('Output = ' + str(result.stdout))
                return False
        return result.stdout
    except subprocess.CalledProcessError as e1:
        logger.info('ProcessError -- ' + str(e1))
    except OSError as e2:
        logger.info('OSError -- ' + str(e2))
    return False

def createPythonEnv(envPath):
    if os.path.exists(envPath+'/bin/' + pythonVersion): # No need to recreate
        return

    cmd = pythonVersion + ' -m venv --system-site-packages  ' + envPath
    logger.info('Creating Python Virtual Environment at: ' + envPath)
    result = runsubprocess(cmd)
    if result != '':
        logger.info ('Problem creating Virtual Environment')
        logger.info(result)
        sys.exit(1)
    return

def getInstalledVersion(m,envPath ):
    # If installed by pip and not a built-in - should return version number
    # If installed but no version number return 0
    # If not installed return -1
    # If a built-in return ''
    try:
        globals()[m] = __import__(m)  #Will likely not work if alternate python versions allowed in future
        result = globals()[m].__version__
        #logger.info('System Version is: ' + result)
        return result

    except AttributeError: # No version number
        return 'Built-In'

    except ImportError: #  Check to see if pip thinks its installed
        if envPath == '':
            cmd = 'python -m pip list'
        else:
            cmd = envPath + '/bin/' + pythonVersion + ' -m pip list'

        request = runsubprocess(cmd)
        if request is False:
            logger.info('Aborting: Failed to get pip list')
            sys.exit(1)
        # Normalise to lower case and underscore
        request = request.lower()
        request = request.replace('-','_')
        reuest = request.replace('.','_')

        if m in request: #  The module exists
            # Try to get version number
            regex = '^'+ m + '\s+(.*)'
            result = re.findall(regex,request,flags=re.MULTILINE)
            if result[0] != '': # version number found
                return result[0]
            # Module found but no version number available
            return '0'
        else:
            return 'None'


def installModule(mRequest, mVersion, envPath):
    upgrade = ''
    if mVersion == '':
        upgrade = ' --upgrade '
    if envPath == '':
        cmd = pythonVersion + ' -m pip install --no-cache-dir ' + upgrade +  '"' + mRequest + '"' 
    else:
        cmd = envPath + '/bin/'+ pythonVersion + ' -m pip install --no-cache-dir ' + upgrade +  '"' + mRequest + '"' 

    result = runsubprocess(cmd)
    if result == False:  # module could not be installed
        return False

    return True

def main(progName):
    # Set up logging so journalc can be used
    createLogger(progName)

    #  Validate that the call was well formed and get the arguments
    requestedVersion, pluginName = validateArguments()
    # Change ro canonical name
    requestedVersion = requestedVersion.lower()
    requestedVersion = requestedVersion.replace('.','_')
    requestedVersion = requestedVersion.replace('-','_')

    if pluginName != '':
        #setup python virtual environment
        venvPath = pluginPath + '/' + pluginName + '/venv'
        createPythonEnv(venvPath)
    else:
        venvPath = '' # Install to system default

    # Get the elements of the requested module - parseVersion may modify
    mName, mCompare, mVersion = parseVersion(requestedVersion)
    mRequested = mName+mCompare+mVersion

    logger.info('Checking for python module: ' + mRequested)
    if pluginName == '':
        logger.info('in System Environment')
    else:
        logger.info('in Virtual Environment: ' + venvPath)

    # Check to see what is installed
    installedVersion = getInstalledVersion(mName, venvPath)
    logger.info('Currently installed: '+ installedVersion)

    #  Determine next action according to Rules
    #  Positionally sensitive
    tryInstall = True
    if pluginName == '':  # System env rules
        if installedVersion == 'Built-In': # Rule 1
            resultCode = 2
            tryInstall = False
        elif installedVersion == 'None':   # Rule 2
            pass
        elif mVersion == '':               # Rule 3
            resultCode = 0
            tryInstall = False
        elif version(installedVersion) >= version(mVersion):
            resultCode = 0                 # Rule 4
            tryInstall = False

    else:  #Venv Rules 
        if installedVersion == 'Built-In': # Rule 1
            resultCode = 2
            tryInstall = False

    if tryInstall:
        installOk = installModule(mRequested, mVersion, venvPath)
        if installOk:
            resultCode = 1
        elif installedVersion not in ['Built_in','None']:
            resultCode = 4
        else:
           resultCode = 3

    # Exit the program with appropriate log entries
    if resultCode == 0:
        logger.info('Module already installed')
        sys.exit(0) #Success
    elif resultCode == 1:
        logger.info('Module ' + mName + ' was installed or updated to version ' +  getInstalledVersion(mName, venvPath))
        sys.exit(0) #Success
    elif resultCode == 2:
        logger.info('Module is a built-in. Nothing to install.')
        sys.exit(0) #Success
    elif resultCode == 3:
        logger.info('Module ' + mRequested + ' could not be installed.')
        logger.info('Check the module name and version number(if provided).')
        sys.exit(1)
    elif resultCode == 4:
        logger.info('Unable to update module: Still at version ' + installedVersion)
    else:
        logger.info('An unexpected error occured')
        sys.exit(1)

if __name__ == "__main__":  # Do not run anything below if the file is imported by another program
    programName = sys.argv[0]
    main(programName)
