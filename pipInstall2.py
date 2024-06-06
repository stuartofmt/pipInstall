#!/usr/bin/env python

"""
Install python modules and create a virtual environment for the plugin.

# Copyright (C) 2023 Stuart Strolin all rights reserved.
# Released under The MIT License. Full text available via https://opensource.org/licenses/MIT

Useage:
Usage pipInstall.py -m <manifest file> -p <plugin path>

Both <manifest file. and <plugin path> are fully qualified

A virtual environment will be created for python at
<plugin Path>/VENV_FOLDER   (see constant section)

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
        1. If the module is a Built-In ==> do nothing

Note: If a module is already installed but failes reinstall / update
      The occurence is logged and the install request is considered successful        

Return Codes:

0 - All modules successfully installed or already installed.
1 = Something nasty happened or one or more modules could not be installed

Verson:
1.0.0
Initial Release
"""


import subprocess
import sys
import logging
from pkg_resources import parse_version as version
import re
import os
import sysconfig
import argparse
import json

# CONSTANTS
VENV_FOLDER = 'venv'
MANIFEST_KEY = 'sbcPythonDependencies'
PIP = 'pip'

if os.name == 'nt': # Windows
    BIN_DIR = 'Scripts'
    PYTHON_VERSION = 'python.exe'
else:
    BIN_DIR = 'bin'
    PYTHON_VERSION = 'python'


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

def validateParams():
    parser = argparse.ArgumentParser(
            description='pipInstall2',
            allow_abbrev=False)
    # Environment
    parser.add_argument('-m', type=str, nargs=1, default=[],
                        help='module path')
    parser.add_argument('-p', type=str, nargs=1, default=[], help='plugin path')

    args = vars(parser.parse_args())  # Save as a dict

    mFile = args['m'][0]
    pPath = args['p'][0]

    if mFile is None:
        logger.info('Exiting: No manifest file (-m) was provided')
        sys.exit(1)
    elif not os.path.isfile(mFile):
        logger.info('Exiting: Manifest file ' +mFile + 'does not exist')
        sys.exit(1)

    if pPath is None:
        logger.info('Exiting: No plugin path (-p) was provided')
        sys.exit(1)
    elif not os.path.isdir(pPath):    
        logger.info('Exiting: Manifest file ' +mFile + 'does not exist')
        sys.exit(1)
        
    return mFile, pPath


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
        pass
        #logger.info('ProcessError -- ' + str(e1))  #  Supress this error 
    except OSError as e2:
        logger.info('OSError -- ' + str(e2))
    return False

def createPythonEnv(envPath):
    pythonFile = os.path.normpath(os.path.join(envPath,BIN_DIR,PYTHON_VERSION))
    print(pythonFile)
    if os.path.isfile(pythonFile): # No need to recreate
        return

    cmd = PYTHON_VERSION + ' -m venv --system-site-packages  ' + envPath
    logger.info('Creating Python Virtual Environment at: ' + envPath)
    result = runsubprocess(cmd)
    if result != '':
        logger.info ('Problem creating Virtual Environment')
        logger.info(result)
        sys.exit(1)
    return

def getModuleList(mFile):
    with open(mFile) as jsonfile:
        config = json.load(jsonfile)

    mList = config[MANIFEST_KEY]

    for i in mList:
        print(i)

    return mList

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
        pythonFile = os.path.normpath(os.path.join(envPath,BIN_DIR,PYTHON_VERSION))
        cmd = pythonFile + ' -m ' + PIP + ' list'

        request = runsubprocess(cmd)
        if request is False:
            logger.info('Aborting: Failed to get pip list')
            sys.exit(1)
        # Normalise to lower case and underscore
        request = request.lower()
        request = request.replace('-','_')

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
    pythonFile = os.path.normpath(os.path.join(envPath,BIN_DIR,PYTHON_VERSION))
    cmd = pythonFile + ' -m ' + PIP + ' install --no-cache-dir ' + upgrade +  '"' + mRequest + '"' 

    result = runsubprocess(cmd)
    if result == False:  # module could not be installed
        return False

    return True

def installModules(mList,envPath):
    sList = []
    fList = []
    for requestedVersion in mList:
        # Get the elements of the requested module - parseVersion may modify
        mName, mCompare, mVersion = parseVersion(requestedVersion)
        # Change to canonical name
        mName = mName.lower()
        mName = mName.replace('-','_')
        mName = mName.replace('.','_')
        mRequested = mName+mCompare+mVersion

        logger.info('Checking for python module: ' + mRequested)

        # Check to see what is installed
        installedVersion = getInstalledVersion(mName, envPath)

        #  Determine next action
        if installedVersion == 'Built-In': # Rule 1
            resultCode = 2
        else:
            installOk = installModule(mRequested, mVersion, envPath)
            if installOk:
                resultCode = 1
            elif installedVersion not in ['Built_in','None']:
                resultCode = 4
            else:
                resultCode = 3

        # Exit the program with appropriate log entries
        if resultCode == 0:
            sList.append('Module "' + mRequested + '" is already installed')
        elif resultCode == 1:
            sList.append('Module "' + mName + '" was installed or updated to version ' +  getInstalledVersion(mName, envPath))
        elif resultCode == 2:
            sList.append('Module "' + mName + '" is a built-in.')
        elif resultCode == 3:
            fList.append('Module "' + mRequested + '" could not be installed.')
        elif resultCode == 4:
            sList.append('Module "' + mName + '" was not updated from version ' + installedVersion)
        else:
            logger.info('An unexpected error occured')
            sys.exit(1)

    return sList, fList

def main(progName):
    #  Set up logging so journalc can be used
    createLogger(progName)

    #  Validate that the call was well formed and get the arguments
    manifestFile, pluginPath = validateParams()
    venvPath = os.path.normpath(os.path.join(pluginPath,VENV_FOLDER))

    #  Create virtual environment
    createPythonEnv(venvPath)

    # parse the manifestfile
    moduleList = getModuleList(manifestFile)

    # Install the modules
    successList = []
    failList = []    
    successList, failList = installModules(moduleList,venvPath)

    if len(successList) > 0:
        logger.info('The following modules were installed or updated:')
        for entry in successList:
            logger.info(entry)

    if len(failList) > 0:
        logger.info('The following modules could not be installed:')
        for entry in failList:
            logger.info(entry)
            sys.exit(1)

if __name__ == "__main__":  # Do not run anything below if the file is imported by another program
    programName = sys.argv[0]
    main(programName)
