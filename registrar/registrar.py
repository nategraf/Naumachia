#!/usr/bin/env python3

from os import path, environ, remove
from enum import Enum
from datetime import datetime
import argparse
import logging
import subprocess
import sys
import re

EASYRSA_ALREADY_EXISTS_MSG = b'Request file already exists'
EASYRSA_ALREADY_REVOKED_MSG = b'Already revoked'

script_dir = path.dirname(__file__)
openvpn_default = path.abspath(path.join(script_dir, '../openvpn/config/{challenge}'))
getclient = path.abspath(path.join(script_dir, "getclient"))

EASYRSA = environ.get("EASYRSA", path.abspath(path.join(script_dir, '../tools/EasyRSA-3.0.3')))
OPENVPN = environ.get("OPENVPN", openvpn_default)
EASYRSA_PKI = environ.get("EASYRSA_PKI", path.join(OPENVPN, "pki"))

class CertificateListing:
    """Representaion of the status of a certificate

    Attributes:
        status (CertificateListing.Status): An enum representing the status of the certificate as valid, expired, or revoked
        expires (datetime): The date and time the certificate will expire
        revoked (datetime): The date and time the certificate was revoked, if it has been revoked, otherwise `None`
        serial (str): The hexidecimal serial number of the certificate
        reason (str): The reason the certifiate was revoked, if it has been revoked, otherwise `None`
        cn (str): The common name of the certificate holder
    """
    ans1_format = "%y%m%d%H%M%SZ"
    index_format = r"(?P<status>[VRE])\s+(?P<expires>[0-9]{12}Z)\s+(?P<revoked>[0-9]{12}Z)?\s*(?P<serial>[0-9A-F]+)\s+(?P<reason>\S+)\s+/CN=(?P<cn>[\w.]+)"

    class Status(Enum):
        VALID = 1
        EXPIRED = 2
        REVOKED = 3

        @classmethod
        def parse(cls, char):
            """Convert a charecter (V, E, or R) into a Status object

            Args:
                char (str): A single charecter, V, E, or R, representing "Valid", "Expired", and "Revoked" respectivly

            Returns:
                CertificiateListing.Status: The coorosponding Status object, or None if the char is invalid
            """
            if char == 'V':
                return cls.VALID
            elif char == 'E':
                return cls.EXPIRED
            elif char == 'R':
                return cls.REVOKED
            else:
                return None

    def __init__(self, status=Status.VALID, expires=None, revoked=None, serial=None, reason=None, cn=None):
        self.status = status
        self.expires = expires
        self.revoked = revoked
        self.serial = serial
        self.reason = reason
        self.cn = cn

    @classmethod
    def parse(cls, line):
        """Parses a line from the easyrsa index.txt file and creates a CertificateListing object

        Args:
            line (str): A line from the easyrsa index.txt file

        Returns:
            CertificateListing: The parsed object, or None if the line is not formated correctly
        """
        match = re.match(cls.index_format, line)
        
        if match is None:
            return None

        groups = match.groupdict()

        revoked_time = None
        if 'revoked' in groups and groups['revoked'] is not None:
            revoked_time = datetime.strptime(groups['revoked'], cls.ans1_format)
        
        vals = {
            'status': cls.Status.parse(groups['status']),
            'expires': datetime.strptime(groups['expires'], cls.ans1_format),
            'revoked': revoked_time,
            'serial': groups['serial'],
            'reason': groups['reason'],
            'cn': groups['cn']
        }

        return cls(**vals)

def add_cert(cn):
    """Creates certificates for a client

    Args:
        cn (str): The common name of the client
    """
    try:
        subprocess.run(
            [path.join(EASYRSA, 'easyrsa'), 'build-client-full', cn, 'nopass'],
            stderr=subprocess.PIPE,
            cwd=OPENVPN,
            check=True
        )
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and EASYRSA_ALREADY_EXISTS_MSG in e.stderr:
            logging.info("Using existing certs for '{}'".format(cn))
        else:
            raise
    else:
        logging.info("Built new certs for '{}'".format(cn))

def get_config(cn):
    """Returns the confgiuration file text for an OpenvVPN client

    Args:
        cn (str): The common name of the client

    Returns:
        str: The file text for the client's OpenVPN client
    """
    config = subprocess.run(
        [getclient, cn],
        stdout=subprocess.PIPE,
        cwd=OPENVPN,
        check=True
    ).stdout.decode('utf-8')

    logging.info("Compiled configuration file for '{}'".format(cn))
    return config

def revoke_cert(cn):
    """Revokes the certificates for a client

    Args:
        cn (str): The common name of the client
    """
    try:
        subprocess.run(
            [path.join(EASYRSA, 'easyrsa'), 'revoke', cn],
            input=b'yes',
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=OPENVPN,
            check=True
        )
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and EASYRSA_ALREADY_REVOKED_MSG in e.stderr:
            logging.info("Already revoked certificate for '{}'".format(cn))
        else:
            raise
    else:
        logging.info("Revoked certificate for '{}'".format(cn))

        subprocess.run(
            [path.join(EASYRSA, 'easyrsa'), 'gen-crl'],
            stdout=subprocess.PIPE,
            cwd=OPENVPN,
            check=True
        )

def list_certs(cn=None):
    """Returns all certificates information, or for a particular client

    Args:
        cn (str): The common name of the client (defaults to None)

    Returns:
        list[CertificateListing]: The certificate information for all certificates on the challenge, or for a specific client if specified
    """
    listing = list()

    with open(path.join(EASYRSA_PKI, 'index.txt')) as index_file:
        for line in index_file:
            entry = CertificateListing.parse(line)
            if entry is not None and (cn is None or entry.cn == cn):
                listing.append(entry)

    return listing

def _try_remove(path):
    try:
        remove(path)
    except FileNotFoundError:
        pass

def remove_cert(cn):
    """Removes certificates and index entries for a specified client

    Args:
        cn (str): The common name of the client (defaults to None)
    """
    for entry in list_certs(cn):
        _try_remove(path.join(EASYRSA_PKI, 'certs_by_serial', entry.serial + '.pem'))
        _try_remove(path.join(EASYRSA_PKI, 'issued', entry.cn + '.crt'))
        _try_remove(path.join(EASYRSA_PKI, 'private', entry.cn + '.key'))
        _try_remove(path.join(EASYRSA_PKI, 'reqs', entry.cn + '.req'))

        new_index_lines = []
        with open(path.join(EASYRSA_PKI, 'index.txt')) as index_file:
            for line in index_file:
                if CertificateListing.parse(line).cn != entry.cn:
                    new_index_lines.append(line)

        with open(path.join(EASYRSA_PKI, 'index.txt'), 'w') as index_file:
            index_file.write('\n'.join(new_index_lines))

def parse_args():
    global EASYRSA
    global OPENVPN
    global EASYRSA_PKI

    parser = argparse.ArgumentParser(
        description = "Manages client certificates and configurations for Naumachia challeneges",
        formatter_class = argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('challenge', help="the short name for the challenge")
    parser.add_argument('--openvpn', metavar='PATH', help="path to the directory for openvpn configurations", default=OPENVPN)
    parser.add_argument('--easyrsa', metavar='PATH', help="path to the directory containing the easyrsa executable", default=EASYRSA)
    subparsers = parser.add_subparsers(dest='action', help="what you wish to do with the client config")

    parser_add = subparsers.add_parser('add', help="create a set of certificates for a client")
    parser_add.add_argument('client', help="name of the client")

    parser_get = subparsers.add_parser('get', help="print an openvpn client configuration file for a client")
    parser_get.add_argument('client', help="name of the client")

    parser_remove = subparsers.add_parser('remove', help="remove the certificates for a client")
    parser_remove.add_argument('client', help="name of the client")

    parser_revoke = subparsers.add_parser('revoke', help="revoke the certificates for a client")
    parser_revoke.add_argument('client', help="name of the client")

    parser_list = subparsers.add_parser('list', help="lists information about clients with certificates")
    parser_list.add_argument('client', nargs='?', default=None, help="name of the client")

    args = parser.parse_args()

    if args.openvpn == openvpn_default:
        args.openvpn = args.openvpn.format(challenge=args.challenge)

    EASYRSA = args.easyrsa
    environ["EASYRSA"] = EASYRSA

    OPENVPN = args.openvpn
    environ["OPENVPN"] = OPENVPN

    if "EASYRSA_PKI" not in environ:
        EASYRSA_PKI = path.join(OPENVPN, "pki")

    return args

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)

    args = parse_args()

    if args.action == 'add':
        add_cert(args.client)

    elif args.action == 'get':
        print(get_config(args.client))

    elif args.action == 'revoke':
        revoke_cert(args.client)

    elif args.action == 'remove':
        remove_cert(args.client)

    elif args.action == 'list':
        for entry in list_certs(args.client):
            print(entry.cn)
