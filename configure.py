#!/usr/bin/env python3

from os import path, makedirs, chmod, listdir
from lazycert import LazyCert
import argparse
import io
import jinja2
import logging
import re
import requests
import subprocess
import sys
import sys
import tarfile
import tempfile
import yaml

logger = logging.getLogger(__name__)
script_dir = path.dirname(path.realpath(__file__))
tools_dir = path.abspath(path.join(script_dir, 'tools'))

wildcard = '*'
defaults = {
    'eve': False,
    'domain': None,
    'challenges_directory': './challenges',
    'challenges': {
        '*': {
            'port': 1194,
            'openvpn_management_port': None,
            'ifconfig': None
        }
    },
    'registrar': {
        'port': 3960,
        'network': 'default',
        'tls_enabled': False,
        'tls_verify_client': False,
        'tls_clients': []
    }
}

GITHUB_RELEASE_API = 'https://api.github.com/repos/OpenVPN/easy-rsa/releases/{:s}'
EASYRSA_TAG="v3.0.6"
EASYRSA_VERSION_PATTERN=re.compile(r'(?:EasyRSA-)?v?((?:\d+\.)*\d+)')
REGISTRAR_CERT_DIR=path

def easyrsa_release(tag=None, timeout=5):
    """
    Get the EasyRSA release information from github at a tag or latest if tag is None
    Returns a dictionary parsed from the GitHub release API (https://developer.github.com/v3/repos/releases/)
    """
    name = 'latest' if tag is None else 'tags/'+tag
    with requests.get(GITHUB_RELEASE_API.format(name), timeout=timeout) as resp:
        resp.raise_for_status()
        return resp.json()

def easyrsa_installations(dir):
    """Get the EasyRSA versions installed. Returns (version tag, path) tuples for each installed version"""
    if path.isdir(dir):
        subdirs = (subdir for subdir in (path.join(dir, name) for name in listdir(dir)) if path.isdir(subdir))
        for subdir in subdirs:
            m = EASYRSA_VERSION_PATTERN.fullmatch(path.basename(subdir))
            if m:
                yield (m.group(1), subdir)

def extract_release(release, dest):
    """Given a release object from the Github API, download and extract the .tgz archive"""
    for asset in release['assets']:
        if asset['name'].endswith('.tgz'):
            download_url = asset['browser_download_url']
            break
    else:
        raise ValueError('no .tgz asset in release')

    if not path.exists(dest):
        makedirs(dest)

    with requests.get(download_url, stream=True) as resp:
        resp.raise_for_status()
        tarball = tarfile.open(fileobj=io.BytesIO(resp.content), mode='r:gz')
        tarball.extractall(path=dest)

def obtain_easyrsa(update=True):
    """Returns the path to the default EasyRSA binary after checking for, and possibly installing, the latest version"""
    installed = tuple(easyrsa_installations(tools_dir))
    latest_install = max(installed) if installed else None

    if update:
        try:
            latest_release = easyrsa_release(EASYRSA_TAG)
            latest_version = EASYRSA_VERSION_PATTERN.fullmatch(latest_release['tag_name']).group(1)

            if latest_install is None or latest_version > latest_install[0]:
                extract_release(latest_release, tools_dir)
                latest_install = max(easyrsa_installations(tools_dir))
                logger.info('Installed EasyRSA %s', latest_version)
        except OSError:
            logger.warning('Failed to update EasyRSA')

    if latest_install is not None:
        return path.join(latest_install[1], 'easyrsa')
    else:
        return None

def apply_defaults(config, defaults):
    # Expand the wildcard
    # Wildcard only makes sense when the value is a dict
    if wildcard in defaults:
        default = defaults[wildcard]
        defaults.update({k: default for k in config if k not in defaults})
        defaults.pop(wildcard)

    for key, default in defaults.items():
        # Handle the case where the key is not in config
        if key not in config:
            config[key] = default

        # Recurisly apply defaults to found dicts if the default is a dict
        elif isinstance(default, dict) and isinstance(config[key], dict):
            apply_defaults(config[key], default)

def read_config(filename):
    with open(filename, 'r') as config_file:
        config = yaml.safe_load(config_file)

    logger.debug("Read from file: %s", config)

    apply_defaults(config, defaults)
    for chal_name, chal_settings in config['challenges'].items():
        if 'commonname' not in chal_settings:
            chal_settings['commonname'] = append_domain(chal_name, config['domain'])

        if 'files' not in chal_settings:
            chal_settings['files'] = [path.join(chal_name, 'docker-compose.yml')]

        # Backwards compatibility for clients before ifconfig_push was replaced with ifconfig.
        if 'ifconfig_push' in chal_settings and chal_settings['ifconfig'] is None:
            logger.warning("Setting ifconfig_push is deprectaed. Please use ifconfig instead.")
            chal_settings['ifconfig'] = chal_settings['ifconfig_push']
            del chal_settings['ifconfig_push']

    logger.debug("Modified: %s", config)

    return config

def parse_args():
    parser = argparse.ArgumentParser(
            description='Parse the Naumachia config file and set up the environment',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--verbosity', '-v', metavar="LEVEL", default="info", choices=('critical', 'error', 'warning', 'info', 'debug'), help="logging level to use")
    parser.add_argument('--config', metavar="PATH", default=path.join(script_dir, 'config.yml'), help='path to Naumachia config file')
    parser.add_argument('--templates', metavar="PATH", default=path.join(script_dir, 'templates'), help='path to the configuration templates')
    parser.add_argument('--registrar_certs', metavar="PATH", default=path.join(script_dir, 'registrar/certs'), help='path to the configuration templates')
    parser.add_argument('--compose', metavar="PATH", default=path.join(script_dir, 'docker-compose.yml'), help='path to the rendered docker-compose output')
    parser.add_argument('--ovpn_configs', metavar="PATH", default=path.join(script_dir, 'openvpn', 'config'), help='path to openvpn configurations')
    parser.add_argument('--easyrsa', metavar="PATH", default=None, help='location of easyrsa executable. If the path does not exist, easyrsa will be installed')

    return parser.parse_args()

def init_pki(easyrsa, directory, cn):
    easyrsa = path.abspath(easyrsa)
    debug = logger.isEnabledFor(logging.DEBUG)
    common_args = {
        'check': True,
        'cwd': directory,
        'stdout': subprocess.PIPE if not debug else None,
        'stderr': subprocess.PIPE if not debug else None,
        'universal_newlines': True
    }

    try:
        logger.info("Initializing public key infrastructure (PKI)")
        subprocess.run([easyrsa, 'init-pki'], **common_args)
        logger.info("Building certificiate authority (CA)")
        subprocess.run([easyrsa, 'build-ca', 'nopass'], input="{}.{}\n".format('ca', cn), **common_args)
        logger.info("Generating Diffie-Hellman (DH) parameters")
        subprocess.run([easyrsa, 'gen-dh'], **common_args)
        logger.info("Building server certificiate")
        subprocess.run([easyrsa, 'build-server-full', cn, 'nopass'], **common_args)
    except subprocess.CalledProcessError as e:
        logger.error("Command '{}' failed with exit code {}".format(e.cmd, e.returncode))
        if e.output:
            logger.error(e.output)

def _render(tpl_path, context):
    dirname, filename = path.split(tpl_path)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(dirname or './')
    ).get_template(filename).render(context)

def render(tpl_path, dst_path, context):
    with open(dst_path, 'w') as f:
        f.write(_render(tpl_path, context))
    logger.info("Rendered {} from {} ".format(dst_path, tpl_path))

def rendertmp(tpl_path, context):
    f = tempfile.NamedTemporaryFile(mode='w+')
    f.write(_render(tpl_path, context))
    f.flush()
    return f

def append_domain(name, domain):
    if domain:
        return '.'.join((name, domain))
    else:
        return name

if __name__ == "__main__":
    args = parse_args()

    # Configure logging
    levelnum = getattr(logging, args.verbosity.upper(), None)
    if not isinstance(levelnum, int):
        raise ValueError('Invalid log level: {}'.format(args.verbosity))

    logging.basicConfig(level=levelnum, format="[%(levelname)s] %(message)s")

    # Load the config from disk
    logger.info("Using config from {}".format(args.config))
    config = read_config(args.config)

    # Ensure easyrsa is installed
    if args.easyrsa is None:
        args.easyrsa = obtain_easyrsa()
        if args.easyrsa is None:
            logger.error('Failed to find or install easyrsa')
            sys.exit(1)

    logger.info('Using easyrsa installation at %s', args.easyrsa)

    # Render the docker-compose file
    template_path = path.join(args.templates, 'docker-compose.yml.j2')
    render(template_path, args.compose, config)

    # Create and missing openvpn config directories
    for name, chal in config['challenges'].items():
        config_dirname = path.join(args.ovpn_configs, name)
        logger.info("Configuring '{}'".format(name))

        if not path.isdir(config_dirname):
            makedirs(config_dirname)
            logger.info("Created new openvpn config directory {}".format(config_dirname))

            init_pki(args.easyrsa, config_dirname, chal['commonname'])
        else:
            logger.info("Using existing openvpn config directory {}".format(config_dirname))

        # Dump the challenge config into the openvpn directory.
        with open(path.join(config_dirname, 'challenge.yml'), 'w') as challenge_file:
            yaml.dump({**chal, 'name': name}, challenge_file, default_flow_style=False)
        logger.info("Wrote challenge config to {}".format(path.join(config_dirname, 'challenge.yml')))

        # Create the openvpn server config for the challenge.
        render(path.join(args.templates, 'openvpn.conf.j2'), path.join(config_dirname, 'openvpn.conf'), {**config, 'challenge': chal})

    # Create certificates for the registrar if needed
    if config['registrar'] and config['registrar']['tls_enabled']:
        logger.info("Setting up certificates for registrar in {}".format(args.registrar_certs))
        if not path.isdir(args.registrar_certs):
            makedirs(args.registrar_certs)

        generator = LazyCert(args.registrar_certs)
        config_template = path.join(args.templates, 'openssl.conf.j2')

        # Create the gencert function here to have config and args in closure
        def gencert(name, ca=None):
            cn = append_domain(name, config['domain'])
            if ca is not None:
                ca = append_domain(ca, config['domain'])

            if not path.isfile(path.join(args.registrar_certs, cn + '.crt')):
                with rendertmp(config_template, {'cn': cn, 'ca': ca is None}) as certconfig:
                    generator.create(cn, ca=ca, config=certconfig.name)
                logger.info("Created new certificate for {}".format(cn))
            else:
                logger.info("Using existing certificate for {}".format(cn))

        gencert('ca')
        gencert('registrar', 'ca')
        for client in config['registrar']['tls_clients']:
            gencert(client, 'ca')
