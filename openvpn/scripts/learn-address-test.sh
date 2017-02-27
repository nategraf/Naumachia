#!/bin/bash

TIMESTAMP=$(date +%x_%H:%M:%S:%N | sed 's/\(:[0-9][0-9]\)[0-9]*$/\1/')
echo "$TIMESTAMP: Learn address call $*"
exit 0
