#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
for file in $(find $SCRIPT_DIR/challenges -name docker-compose.yml); do
    pushd $(dirname $file)
    sudo docker compose build $@
    popd
done
