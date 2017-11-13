#!/usr/bin/env python3

import io
import jinja2
import yaml
import argparse
import requests
import tarfile
from os import path, mkdir, chmod

EASYRSA_URL='https://github.com/OpenVPN/easy-rsa/releases/download/v3.0.3/EasyRSA-3.0.3.tgz'

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
    parser.add_argument('--easyrsa', metavar="PATH", default=path.join(dir, 'tools', 'easyrsa'), help='location of easyrsa executable. If the path does not exist, easyrsa will be installed')

    return parser.parse_args()

def install_easyrsa(location):
    install_dir = path.dirname(location)
    if not path.isdir(install_dir):
        mkdir(install_dir)

    with requests.get(EASYRSA_URL, stream=True) as resp:
        tarball = tarfile.open(fileobj=io.BytesIO(resp.content), mode='r:gz')

    executable = tarball.extractfile('EasyRSA-3.0.3/easyrsa')

    with open(location, 'wb') as f:
        f.write(executable.read())

    chmod(location, 0o775)

    print("Installed easyrsa to '{}' from '{}'".format(location, EASYRSA_URL))

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

    settings = None
    print("Using settings from {}".format(args.config))
    with open(args.config, 'r') as config_file:
        settings = yaml.load(config_file)

    # Ensure easyrsa is installed
    if not path.exists(args.easyrsa):
        install_easyrsa(args.easyrsa)

    # Render the docker-compose file
    template_path = path.join(args.templates, 'docker-compose.yml.j2')
    render(template_path, args.compose, settings)

    # Create and missing openvpn config directories
    for chal in settings['challenges']:
        config_dirname = path.join(args.ovpn_configs, chal["short_name"])

        if not path.isdir(config_dirname):
            mkdir(config_dirname)
            print("Created new openvpn config directory {}".format(config_dirname))

            context = {'chal': chal}
            context.update(settings)

            render(path.join(args.templates, 'ovpn_env.sh.j2'), path.join(config_dirname, 'ovpn_env.sh'), context)
            render(path.join(args.templates, 'openvpn.conf.j2'), path.join(config_dirname, 'openvpn.conf'), context)

        else:
            print("Using existing openvpn config directory {}".format(config_dirname))
