#!/usr/bin/env python3

from os import path, environ
import argparse
import logging
import subprocess
import sys

EASYRSA_ALREADY_EXISTS_MSG = b'Request file already exists'

script_dir = path.dirname(__file__)
openvpn_default = path.abspath(path.join(script_dir, '../openvpn/config/{challenge}'))
getclient = path.abspath(path.join(script_dir, "getclient"))

EASYRSA = environ.get("EASYRSA", path.abspath(path.join(script_dir, '../tools/EasyRSA-3.0.3/easyrsa')))
OPENVPN = environ.get("OPENVPN", openvpn_default)

def ovpn_config(cn):
    run_args = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'cwd': OPENVPN,
        'check': True
    }

    logging.info("Client configuration Request recieved for '{}'".format(cn))
    try:
        subprocess.run([EASYRSA, 'build-client-full', cn, 'nopass'], **run_args)
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and EASYRSA_ALREADY_EXISTS_MSG in e.stderr:
            logging.info("Using existing certs for '{}'".format(cn))
        else:
            logging.error("Building certs for '{}' failed with exit code {} : EXITING".format(cn, e.returncode))
            raise RuntimeError("'easyrsa build-client-full' commnad returned error code {}\n{}".format(e.returncode, e.output)) from e
    else:
        logging.info("Built new certs for '{}'".format(cn))

    try:
        return subprocess.run([getclient, cn], **run_args).stdout.decode('utf-8')
    except subprocess.CalledProcessError as e:
        raise RuntimeError("'easyrsa build-client-full' commnad returned error code {}\n{}".format(e.returncode, e.output)) from e

def parse_args():
    global EASYRSA
    global OPENVPN

    parser = argparse.ArgumentParser(
        description = "Manages client certificates and configurations for Naumachia challeneges",
        formatter_class = argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('challenge', help="the short name for the challenge")
    parser.add_argument('client', help="name of the client")
    parser.add_argument('--openvpn', metavar='PATH', help="path to the directory for openvpn configurations", default=OPENVPN)
    parser.add_argument('--easyrsa', metavar='PATH', help="path to the easyrsa executable", default=EASYRSA)

    args = parser.parse_args()

    if args.openvpn == openvpn_default:
        args.openvpn = args.openvpn.format(challenge=args.challenge)

    if EASYRSA != args.easyrsa:
        EASYRSA = args.easyrsa
        environ['EASYRSA'] = EASYRSA

    if OPENVPN != args.openvpn:
        OPENVPN = args.openvpn
        environ['OPENVPN'] = OPENVPN

    return args

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)

    args = parse_args()

    print(ovpn_config(args.client))
