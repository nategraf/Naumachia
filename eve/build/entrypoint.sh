#!/bin/bash
set -e

if [ ! -f /dev/net/tun ]; then
    mkdir /dev/net
    mknod /dev/net/tun c 10 200
fi

exec "$@"
