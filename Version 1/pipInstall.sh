#!/bin/bash

#Simplified Version - does not include safeguards / handling
#provided by the python script pipInstall.py 

#Called with two arguments
#first - module/version to be installed
#second - plugin name

#all venv are installed under a common folder
#this avoided issues with existing plugin management code
# e.g. deleting plugin folders
 
#each plugin has a separate venv with the same name as the plugin
#venv share the system packages - so same python version as system default
#i.e. created with the --system-site-packages option 
#this avoided several highly technical issues regarding common C modules

module=$1
pluginname=$2

#TEST PURPOSES ONLY
pluginname='duetBackup'

#Separate venv  by plugin name 
basedir='/opt/dsf/plugins'
venvdir=$basedir/$pluginname/venv
pythondir=$venvdir/bin

# Make sure parameters were provided
if [ '$module' == '' ] ; then
  echo 'Module name is missing'
  exit 1
fi

if [ '$pluginname' == '' ] ; then
  echo 'Plugin name is missing'
  exit 1
fi

echo 'Installing '$module' into '$venvdir
#Create basedir if necessary
if [ ! -d $basedir ]; then
  echo 'Creating '$basedir
  mkdir $basedir
fi

#Create plugin specific venv if it does not exist
if [ ! -f $pythondir/python ]; then
  python -m venv --system-site-packages $venvdir
fi

# Install the module
$pythondir/pip install --no-cache-dir $module
exitcode=$?

case $exitcode in
  '0')
    echo 'Module '$module' installed'
    exit 0
  ;;
  '1')
   echo 'Module '$module' is built-in or an error occured'
   exit 0
  ;;
esac
exit $exitcode

