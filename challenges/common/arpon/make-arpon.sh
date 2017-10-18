#!/bin/sh

set -e

echo "Building ArpON from $ARPON_REPO_URL"

mkdir build-tmp
cd build-tmp

git clone "$ARPON_REPO_URL" arpon
if [ -z "$(ls arpon)" ]; then
    echo "BUILD FAILED: Could not clone $ARPON_REP_URL"
    exit 1
fi

cd arpon

if [ -n "$ARPON_REPO_BRANCH" ]; then
    git checkout "$ARPON_REPO_BRANCH"
fi

mkdir build && cd build

cmake .. && make && make install

cd ../../..

rm -rf build-tmp
