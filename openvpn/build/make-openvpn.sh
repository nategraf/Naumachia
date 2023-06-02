#!/bin/sh

set -e

if [ -z "$OVPN_REPO_URL" ]; then
   OVPN_REPO_URL="https://github.com/OpenVPN/openvpn.git" 
fi

echo "Building OpenVPN from $OVPN_REPO_URL"

mkdir build-tmp
cd build-tmp

git clone "$OVPN_REPO_URL" openvpn
if [ -z "$(ls openvpn)" ]; then
    echo "BUILD FAILED: Could not clone $OVPN_REPO_URL"
    exit 1
fi

cd openvpn

if [ -n "$OVPN_REPO_BRANCH" ]; then
    echo "Checking out branch $OVPN_REPO_URL"
    git checkout "$OVPN_REPO_BRANCH"
fi

autoreconf -i -v -f
./configure --disable-lz4 --disable-lzo && make && make install

cd ..

cd .. 
rm -rf build-tmp
