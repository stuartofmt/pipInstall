#!/bin/bash
if [ ! -f pipInstall2.py ]; then
    echo Change to the directory with pipInstall2.py
fi

python $(pwd)/pipInstall2.py -m $(pwd)/normal_test.json -p $(pwd)
code=$?

# Packages installed in the venv (packages the venv uses from the system python are not listed)
# Read from the .dist-info folders because pip list hides some names (e.g. argparse)
echo
echo "Packages installed in $(pwd)/venv:"
for d in $(pwd)/venv/lib/python*/site-packages/*.dist-info; do
    b=$(basename "$d" .dist-info)
    printf '    %-30s %s\n' "${b%-*}" "${b##*-}"
done

echo
echo "pipInstall2 exit code: $code"
exit $code
