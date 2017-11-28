from argparse import ArgumentParser
from os import path, envriron
import logging
import subprocess
import sys

logging.basicConfig(level=logging.DEBUG)

EASYRSA_ALREADY_EXISTS_MSG = b'Request file already exists'

script_dir = path.dirname(__file__)

EASYRSA = environ.get("EASYRSA", path.normpath(path.join(dir, '../tools/esayrsa')))
OPENVPN = environ.get("OPENVPN", None)


def ovpn_config(cn):
    logging.info("Client configuration Request recieved for '{}'".format(cn))
    try:
        subprocess.check_output([EASYRSA, 'build-client-full', cn, 'nopass'], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and EASYRSA_ALREADY_EXISTS_MSG in e.stderr:
            logging.info("Using existing certs for '{}'".format(cn))
        else:
            logging.error("Building certs for '{}' failed with exit code {} : EXITING".format(cn, e.returncode))
            raise RuntimeError("'easyrsa build-client-full' commnad returned error code {}".format(e.returncode)) from e
    else:
        logging.info("Built new certs for '{}'".format(cn))

    try:
        return subprocess.check_output(['getclient', cn])
    except subprocess.CalledProcessError as e:
        raise RuntimeError("'getclient' command returned error code {}".format(e.returncode)) from e

def parse_args():
    openvpn_default = path.normpath(path.join(dir, '../openvpn/config/{challenge}'))

    parser = ArgumentParser(description="Manages client certificates and configurations for Naumachia challeneges")
    parser.add_argument('client', help="name of the client")
    parser.add_argument('challenge', help="the short name for the challenge")
    parser.add_argument('openvpn', metavar='PATH', help="path to the directory for openvpn configurations", default=OPENVPN or openvpn_default)
    parser.add_argument('easyrsa', metavar='PATH', help="path to the easyrsa executable", default=EASYRSA)

    if args.openvpn == openvpn_default:
        args.openvpn = args.openvpn.format(args.challenge)

    args = parser.parse_args()

    if EASYRSA != args.easyrsa:
        EASYRSA = args.easyrsa
        environ['EASYRSA'] = EASYRSA

    if OPENVPN != args.openvpn:
        OPENVPN = args.openvpn
        environ['OPENVPN'] = OPENVPN

    return args

if __name__ == "__main__":
    args = parse_args()

    print(ovpn_config(args.client))
