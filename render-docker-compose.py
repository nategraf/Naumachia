#!/usr/bin/env python3

import jinja2
import os
import yaml

TEMPLATE = "docker-compose.yml.j2"
CONFIG = "config.yml"
RENDERED = "docker-compose.yml"

def render(tpl_path, context):
    path, filename = os.path.split(tpl_path)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(path or './')
    ).get_template(filename).render(context)

if __name__ == "__main__":
    dir = os.path.dirname(__file__)
    template_path = os.path.abspath(os.path.join(dir, TEMPLATE))
    config_path = os.path.abspath(os.path.join(dir, CONFIG))
    rendered_path = os.path.abspath(os.path.join(dir, RENDERED))

    context = None
    with open(config_path, 'r') as config_file:
        context = yaml.load(config_file)

    with open(rendered_path, 'w') as rendered_file:
        rendered_file.write(render(template_path, context))

    print("{} rendered from {} with context from {}".format(RENDERED, TEMPLATE, CONFIG))
