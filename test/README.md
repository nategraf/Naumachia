# System and Load Testing [WIP]

This directory contains system and load testing code for Naumachia.

This a system testing system consisting of a number of workers, a certificate loader, and a redis database. Together these compoents are able to simulate a number of users playing challenges on Naumachia.

The central component is an automated solver which can connect to Naumachia and solve a challenge given a strategy specified as Python code.

Currently there are solutions for:

* middle
* listen

## Run Instructions

1. Modify `loader/config.yml` to specify a number of certificates to generate and use for each challenge, and therefore how many unique clients you will simulate. On boot the loader will ensure that the specified number of openvpn configurations are loaded into the Redis.
2. `docker-compose up --scale worker=$X` where `$X` is the number of of workers you wish to run in parallel.
