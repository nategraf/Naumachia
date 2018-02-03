#!/usr/bin/env python3

import io
import jinja2
import sys
import yaml
import argparse
import subprocess
import requests
import tarfile
from os import path, makedirs, chmod

global_defaults = {
    'DEBUG': False,
    'domain': None,
    'challenges': {},
    'registrar': True,
    'registrar_port': 3960,
    'registrar_network': 'default'
}

challenge_defaults = {
    'port': 1194
}

EASYRSA_URL='https://github.com/OpenVPN/easy-rsa/releases/download/v3.0.3/EasyRSA-3.0.3.tgz'
EASYRSA_DIR='EasyRSA-3.0.3'
EASYRSA_DEFAULT=path.abspath(path.join(path.dirname(__file__), 'tools', EASYRSA_DIR, 'easyrsa'))

def install_easyrsa():
    install_dir = path.abspath(path.join(path.dirname(__file__), 'tools'))

    if not path.isdir(install_dir):
        makedirs(install_dir)

    with requests.get(EASYRSA_URL, stream=True) as resp:
        tarball = tarfile.open(fileobj=io.BytesIO(resp.content), mode='r:gz')
        tarball.extractall(path=install_dir)

    print("Installed easyrsa to '{}' from '{}'".format(install_dir, EASYRSA_URL))

def read_config(filename):
    with open(filename, 'r') as config_file:
        settings = yaml.load(config_file)

    for key, default in global_defaults.items():
        if key not in settings:
            settings[key] = default

    for chal_name, chal_settings in settings['challenges'].items():
        for key, default in challenge_defaults.items():
            if key not in chal_settings:
                chal_settings[key] = default

            if 'commonname' not in chal_settings:
                if settings['domain']:
                    chal_settings['commonname'] = '.'.join((chal_name, settings['domain']))
                else:
                    chal_settings['commonname'] = chal_name

    return settings

def parse_args():
    dir = path.dirname(__file__)

    parser = argparse.ArgumentParser(
            description='Parse the Naumachia config file and set up the environment',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--config', metavar="PATH", default=path.join(dir, 'config.yml'), help='path to Naumachia config file')
    parser.add_argument('--templates', metavar="PATH", default=path.join(dir, 'templates'), help='path to the configuration templates')
    parser.add_argument('--compose', metavar="PATH", default=path.join(dir, 'docker-compose.yml'), help='path to the rendered docker-compose output')
    parser.add_argument('--ovpn-configs', metavar="PATH", default=path.join(dir, 'openvpn', 'config'), help='path to openvpn configurations')
    parser.add_argument('--easyrsa', metavar="PATH", default=EASYRSA_DEFAULT, help='location of easyrsa executable. If the path does not exist, easyrsa will be installed')

    return parser.parse_args()

def init_pki(easyrsa, directory, cn):
    easyrsa = path.abspath(easyrsa)
    common_args = {
        'check': True,
        'cwd': directory,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'universal_newlines': True
    }

    try:
        print("Initializing public key infrastructure (PKI)")
        subprocess.run([easyrsa, 'init-pki'], **common_args)
        print("Building certificiate authority (CA)")
        subprocess.run([easyrsa, 'build-ca', 'nopass'], input="{}.{}\n".format('ca', cn), **common_args)
        print("Generating Diffie-Hellman (DH) parameters")
        subprocess.run([easyrsa, 'gen-dh'], **common_args)
        print("Building server certificiate")
        subprocess.run([easyrsa, 'build-server-full', cn, 'nopass'], **common_args)
        print("Generating certificate revocation list (CRL)")
        subprocess.run([easyrsa, 'gen-crl'], **common_args)
    except subprocess.CalledProcessError as e:
        print("Command '{}' failed with exit code {}".format(e.cmd, e.returncode))
        print(e.output)

def render(tpl_path, dst_path, context):
    dirname, filename = path.split(tpl_path)
    result = jinja2.Environment(
        loader=jinja2.FileSystemLoader(dirname or './')
    ).get_template(filename).render(context)

    with open(dst_path, 'w') as f:
        f.write(result)

    print("Rendered {} from {} ".format(dst_path, tpl_path))

    return result


if __name__ == "__main__":
    args = parse_args()

    print("Using settings from {}".format(args.config))
    settings = read_config(args.config)

    # Ensure easyrsa is installed
    if not path.exists(args.easyrsa):
        if args.easyrsa == EASYRSA_DEFAULT:
            install_easyrsa()
        else:
            raise FileNotFoundError(args.easyrsa)

    # Render the docker-compose file
    template_path = path.join(args.templates, 'docker-compose.yml.j2')
    render(template_path, args.compose, settings)

    # Create and missing openvpn config directories
    for name, chal in settings['challenges'].items():
        config_dirname = path.join(args.ovpn_configs, name)
        print("\nConfiguring '{}'".format(name))

        if not path.isdir(config_dirname):
            makedirs(config_dirname)
            print("Created new openvpn config directory {}".format(config_dirname))

            init_pki(args.easyrsa, config_dirname, chal['commonname'])
        else:
            print("Using existing openvpn config directory {}".format(config_dirname))

        context = {'chal': chal}
        context.update(settings)

        render(path.join(args.templates, 'ovpn_env.sh.j2'), path.join(config_dirname, 'ovpn_env.sh'), context)
        render(path.join(args.templates, 'openvpn.conf.j2'), path.join(config_dirname, 'openvpn.conf'), context)
