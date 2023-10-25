#!/usr/bin/env python3
"""
Barebones script to generate OpenRVDAS config file from minimal input file
using a Jinja template.

Can be run from the command line as follows:
```
   python cruise_config_generator.py\
        --voyage_details tests\cruise_devices.yaml\
        --template tests\cruise_template.jinja\
        --config_output tests\sample_cruise.yaml
```

Author: Hugh Barker
Organisation: CSIRO
Vessel: Investigator
Date: June 2022
"""
import yaml
import argparse
from jinja2 import Template

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Create an OpenRVDAS config file using jinja templates')

    parser.add_argument('--voyage_details', required=True,
                        help='Input voyage configuration yaml -\
                             voyage details and a list of devices')
    parser.add_argument('--template', required=True,
                        help='jinja2 template used to create full configuration')
    parser.add_argument('--config_output', required=True,
                        help='File to output full configuration yaml to')

    args = parser.parse_args()

    with open(args.voyage_details) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    with open(args.template) as f:
        template = Template(f.read(), trim_blocks=True, lstrip_blocks=True)

    config = template.render(data)

    with open(args.config_output, 'w') as f:
        f.write(config)
