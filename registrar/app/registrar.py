from datetime import datetime
from enum import Enum
from os import path, environ, remove, listdir
import base64
import binascii
import jinja2
import json
import logging
import re
import subprocess
import sys
import yaml
import zencode

EASYRSA_ALREADY_EXISTS_MSG = b'file already exists'
EASYRSA_ALREADY_REVOKED_MSG = b'Already revoked'
EASYRSA_NONEXIST_REVOKE_MSG = b'Unable to revoke as the input file is not a valid certificate'
EASYRSA_NONEXIST_GET_MSG = b'Unable to find'
EASYRSA_VERSION_PATTERN=re.compile(r'(?:EasyRSA-)?v?((?:\d+\.)*\d+)')

script_dir = path.dirname(path.realpath(__file__))
tools_dir = path.abspath(path.join(script_dir, '../../tools'))
client_template = path.abspath(path.join(script_dir, "client.ovpn.j2"))

def easyrsa_installation(dir):
    """Get the latest EasyRSA versions installed. Returns the path for the latest version or None"""
    latest = ("0.0", None)
    if path.isdir(dir):
        subdirs = (subdir for subdir in (path.join(dir, name) for name in listdir(dir)) if path.isdir(subdir))
        for subdir in subdirs:
            m = EASYRSA_VERSION_PATTERN.fullmatch(path.basename(subdir))
            if m:
                latest = max(latest, (m.group(1), subdir))
    return latest[1]

OPENVPN_BASE = environ.get("OPENVPN_BASE", path.abspath(path.join(script_dir, '../../openvpn/config')))
EASYRSA = environ.get("EASYRSA") or easyrsa_installation(tools_dir)

def mask(slash):
   """creates a subnet mask from the given slash notation int"""
   if slash < 0 or slash > 32:
       raise ValueError("slash notation ipv4 subnet masks must be in range [0, 32]")

   x = (0xffffffff << (32 - slash)) & 0xffffffff
   return '.'.join(str((x & (0xff << s)) >> s) for s in (24, 16, 8, 0))

def expand_cidr(cidr):
    """expand a cidr fromatted addr into an addr and mask string

    Example::
      >>> expand_cidr("192.168.1.1/24")
      ... ('192.168.1.1', '255.255.255.0')
      >>> expand_cidr("172.10.10.5/28")
      ... ('192.168.1.1', '255.255.255.240')
    """
    m = re.fullmatch(r'(?P<addr>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/(?P<mask>\d+)', cidr)
    if not m:
        raise ValueError(f"{cidr!s} is not an ipv4 cidr formatted address")

    addr, slash = m.group('addr', 'mask')
    return addr, mask(int(slash))

def render(tpl_path, context):
    dirname, filename = path.split(tpl_path)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(dirname or './')
    ).get_template(filename).render(context)

def extract_certificate(text):
    """extract the encoded certificate from an x509 certificate file"""
    match = re.search(r'-+BEGIN CERTIFICATE-+.*-+END CERTIFICATE-+\n?', text, re.RegexFlag.DOTALL)
    if match is None:
        raise ValueError("given text does not contain a certificate")
    return match.group(0)

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
    index_format = r"(?P<status>[VRE])\s+(?P<expires>[0-9]{12}Z)\s+(?P<revoked>[0-9]{12}Z)?\s*(?P<serial>[0-9A-F]+)\s+(?P<reason>\S+)\s+/CN=(?P<cn>[\w .]+)"

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

class EntryNotFoundError(Exception):
    def __init__(self, cn):
        self.cn = cn

    def __str__(self):
        return "No entry for '{0}' was found".format(self.cn)

class Registrar:
    """Handles certificate and configuration management for a challenge

    Attributes:
        chal (str): Name of the challenge this instance manages
        openvpn_dir (str): Path to the directory containing OpenVPN files
        easyrsa_dir (str): Path to the directory containing EasyRSA tools
    """
    def __init__(self, chal, openvpn_dir=None, easyrsa_dir=None, pki_dir=None):
        self.chal = chal

        if openvpn_dir is None:
            self.openvpn_dir = path.join(OPENVPN_BASE, chal)
        else:
            self.openvpn_dir = openvpn_dir

        if easyrsa_dir is None:
            self.easyrsa_dir = EASYRSA
        else:
            self.easyrsa_dir = easyrsa_dir

    @property
    def easyrsa(self):
        """Get the path to the EasyRSA executable"""
        return path.join(self.easyrsa_dir, 'easyrsa')

    @property
    def easyrsa_pki(self):
        """Get the path to the EasyRSA pki folder"""
        return path.join(self.openvpn_dir, 'pki')

    @property
    def challenge_config(self):
        """Get the path to the challnge config file"""
        return path.join(self.openvpn_dir, 'challenge.yml')

    @property
    def _run_env(self):
        return {
            "OPENVPN": self.openvpn_dir,
            "EASYRSA": self.easyrsa_dir,
            "EASYRSA_PKI": self.easyrsa_pki
        }

    def _run(self, cmdargs, handler=None, **kwargs):
        try:
            return subprocess.run(
                cmdargs,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                check=True,
                cwd=self.openvpn_dir,
                env=self._run_env,
                **kwargs
            )
        except subprocess.CalledProcessError as e:
            if handler is None or not handler(e):
                logging.error(e.stderr.decode('utf-8'))
                raise
            else:
                return None

    def read_challenge_config(self):
        with open(self.challenge_config, 'r') as config:
            return yaml.load(config)

    def add_cert(self, cn):
        """Creates certificates for a client

        Args:
            cn (str): The common name of the client
        """
        cn = zencode.encode(cn)

        proc = self._run(
            [self.easyrsa, 'build-client-full', cn, 'nopass'],
            lambda e: e.returncode == 1 and EASYRSA_ALREADY_EXISTS_MSG in e.stderr,
        )
        if proc:
            logging.info("Using existing certs for {0}".format(cn))
        else:
            logging.info("Built new certs for {0}".format(cn))

    def get_config(self, cn):
        """Returns the confgiuration file text for an OpenvVPN client

        Args:
            cn (str): The common name of the client

        Returns:
            str: The file text for the client's OpenVPN client
        """
        cn = zencode.encode(cn)

        def get_error_handler(e):
            if e.returncode == 1:
                if EASYRSA_NONEXIST_GET_MSG in e.stderr:
                    raise EntryNotFoundError(cn)
            return False

        def read(filepath):
            with open(filepath, 'r') as f:
                return f.read()

        config = render(client_template, {
            'challenge': self.read_challenge_config(),
            'client': {
                'key': read(path.join(self.easyrsa_pki, 'private', cn + '.key')),
                'certificate': extract_certificate(read(path.join(self.easyrsa_pki, 'issued', cn + '.crt'))),
            },
            'ca': {
                'certificate': read(path.join(self.easyrsa_pki, 'ca.crt')),
            },
            'expand_cidr': expand_cidr,
        })
        logging.info("Compiled configuration file for '{}'".format(cn))
        return config

    def revoke_cert(self, cn):
        """Revokes the certificates for a client

        Args:
            cn (str): The common name of the client
        """
        cn = zencode.encode(cn)

        def revoke_error_handler(e):
            if e.returncode == 1:
                if EASYRSA_ALREADY_REVOKED_MSG in e.stderr:
                    return True
                if EASYRSA_NONEXIST_REVOKE_MSG in e.stderr:
                    raise EntryNotFoundError(cn)
            return False

        proc = self._run(
            [self.easyrsa, 'revoke', cn],
            revoke_error_handler,
            input=b'yes',
        )
        if proc:
            logging.info("Revoked certificate for '{}'".format(cn))
        else:
            logging.info("Already revoked certificate for '{}'".format(cn))

            self._run(
                    [self.easyrsa, 'gen-crl'],
            )

    def list_certs(self, cn=None):
        """Returns all certificates information, or for a particular client

        Args:
            cn (str): The common name of the client (defaults to None)

        Returns:
            list[CertificateListing]: The certificate information for all certificates on the challenge, or for a specific client if specified
        """
        if cn:
            cn = zencode.encode(cn)

        listing = list()

        with open(path.join(self.easyrsa_pki, 'index.txt')) as index_file:
            for line in index_file:
                entry = CertificateListing.parse(line)
                if entry is not None and (cn is None or entry.cn == cn):
                    try:
                        entry.cn = zencode.decode(entry.cn)
                    except ValueError:
                        pass # This is not an encoded name

                    listing.append(entry)

        return listing

    def _try_remove(self, path):
        try:
            remove(path)
        except FileNotFoundError:
            pass

    def remove_cert(self, cn):
        """Removes certificates and index entries for a specified client

        Args:
            cn (str): The common name of the client (defaults to None)
        """
        cn = zencode.encode(cn)

        for entry in self.list_certs(cn):
            self._try_remove(path.join(self.easyrsa_pki, 'certs_by_serial', entry.serial + '.pem'))

        self._try_remove(path.join(self.easyrsa_pki, 'issued', cn + '.crt'))
        self._try_remove(path.join(self.easyrsa_pki, 'private', cn + '.key'))
        self._try_remove(path.join(self.easyrsa_pki, 'reqs', cn + '.req'))

        new_index_lines = []
        with open(path.join(self.easyrsa_pki, 'index.txt')) as index_file:
            for line in index_file:
                entry = CertificateListing.parse(line)
                if entry is not None and entry.cn != cn:
                    new_index_lines.append(line)

        with open(path.join(self.easyrsa_pki, 'index.txt'), 'w') as index_file:
            index_file.write(''.join(new_index_lines))

class RegistrarEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, CertificateListing):
            return {
                'status': obj.status,
                'expires': obj.expires,
                'revoked': obj.revoked,
                'serial': obj.serial,
                'reason': obj.reason,
                'cn': obj.cn
            }
        elif isinstance(obj, CertificateListing.Status):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.strftime(CertificateListing.ans1_format)
        else:
            return json.JSONEncoder.default(self, obj)
