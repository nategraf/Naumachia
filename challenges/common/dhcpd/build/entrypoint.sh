#!/usr/bin/env bash

source dhcpd_envs.sh
envsubst </dhcpd.conf.template >/etc/dhcp/dhcpd.conf
echo "$@"
exec "$@"
