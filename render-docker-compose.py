#!/usr/bin/env python3

import jinja2
import yaml
import argparse
from os import path

def parse_args():
    dir = path.dirname(__file__)

    parser = argparse.ArgumentParser(
            description='Parse the Naumachia config file and set up the environment',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--config', metavar="PATH", default=path.join(dir, 'config.yml'), help='path to Naumachia config file')
    parser.add_argument('--template', metavar="PATH", default=path.join(dir, 'docker-compose.yml.j2'), help='path to the docker-compose template')
    parser.add_argument('--rendered', metavar="PATH", default=path.join(dir, 'docker-compose.yml'), help='path to the rendered docker-compose output')

    return parser.parse_args()

def render(tpl_path, context):
    dirname, filename = path.split(tpl_path)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(dirname or './')
    ).get_template(filename).render(context)

if __name__ == "__main__":
    args = parse_args()

    context = None
    with open(args.config, 'r') as config_file:
        context = yaml.load(config_file)

    with open(args.rendered, 'w') as rendered_file:
        rendered_file.write(render(args.template, context))

    print("{} rendered from {} with context from {}".format(args.rendered, args.template, args.config))
