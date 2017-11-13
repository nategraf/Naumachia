#!/usr/bin/env python3

import jinja2
import yaml
import argparse
from os import path, mkdir

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

    return parser.parse_args()

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

    template_path = path.join(args.templates, 'docker-compose.yml.j2')
    render(template_path, args.compose, settings)

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
