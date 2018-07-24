#!/usr/bin/env python3
# coding: utf-8
from os import path, getcwd
import argparse
import subprocess
import logging

logger = logging.getLogger(__name__)

class LazyCert:
    keyfmt = '{cn!s}.key'
    certfmt = '{cn!s}.crt'
    csrfmt = '{cn!s}.csr'
    serialfmt = '{cn!s}.srl'

    def __init__(self, directory, openssl='openssl'):
        self.directory = directory
        self.openssl = openssl

    def _run(self, cmdargs, handler=None, **kwargs):
        try:
            return subprocess.run(
                cmdargs,
                check=True,
                cwd=self.directory,
                **kwargs
            )
        except subprocess.CalledProcessError as e:
            if handler is None or not handler(e):
                if e.stderr:
                    logger.error(e.stderr.decode('utf-8'))
                raise
            else:
                return None

    def create(self, cn, ca=None, config=None):
        """Create a new certificate

        Args:
            cn (str): common name for the cert you want to create
            ca (str): common name for the ca you want to sign with
                if not specified, this will create a self-signed cert
            config (str): path to the config file to use for creating the csr
                if not specified, read from standard input
        """
        key = self.keyfmt.format(cn=cn)
        self._run((self.openssl, 'genrsa', '-out', key, '2048'))

        cert = self.certfmt.format(cn=cn)
        if ca is None:
            if config is None:
                self._run((self.openssl, 'req', '-new', '-x509', '-key', key, '-out', cert))
            else:
                self._run((self.openssl, 'req', '-new', '-x509', '-key', key, '-out', cert, '-config', config))
        else:
            csr = self.csrfmt.format(cn=cn)
            if config is None:
                self._run((self.openssl, 'req', '-new', '-key', key, '-out', csr))
            else:
                self._run((self.openssl, 'req', '-new', '-key', key, '-out', csr, '-config', config))

            cacert = self.certfmt.format(cn=ca)
            cakey = self.keyfmt.format(cn=ca)
            serial = self.serialfmt.format(cn=ca)

            self._run((self.openssl, 'x509', '-req', '-in', csr, '-CA', cacert, '-CAkey', cakey, '-CAserial', serial, '-CAcreateserial', '-out', cert, '-days', '365'))

def parse_args():
    parser = argparse.ArgumentParser(
        description = "A simple utility for creating certificates for use internally to Naumachia",
        formatter_class = argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('cn', metavar='NAME', help="common name for the cert")
    parser.add_argument('--ca', metavar='NAME', help="common name for the ca to sign this cert with", default=None)
    parser.add_argument('--config', metavar='PATH', help="config file to use for generating the csr", default=None)
    parser.add_argument('--verbosity', '-v', metavar='LEVEL', help="the log level to use", choices=('debug', 'info', 'warning', 'error', 'critical'), default='info')

    return parser.parse_args()

def set_loglevel(levelname):
    levelnum = getattr(logging, levelname.upper(), None)
    if not isinstance(levelnum, int):
        raise ValueError('Invalid log level: {}'.format(levelname))

    logging.basicConfig(level=levelnum)

if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(format="[%(levelname)s %(asctime)s] %(message)s", datefmt="%m-%d %H:%M:%S")
    set_loglevel(args.verbosity)

    LazyCert(getcwd()).create(args.cn, args.ca, args.config)
