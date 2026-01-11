#!/bin/bash
if [ ! -f pipInstall2.py ]; then
    echo Change to the directory with pipInstall2.py
fi
python $(pwd)/pipInstall2.py -m $(pwd)/test.json -p $(pwd)
