# Configuration Generator
Given a Jinja template and a yaml file of devices, generate the full cruise yaml configuration file.

## Pre-requisites:

### Jinja2
Install with pip

`pip install Jinja2`

Documentation available at https://jinja.palletsprojects.com/

## To use Config Generator

Create a Jinja template for your cruise definition file. Sample template can be found in tests directory.

Create a devices.yaml file specifying the variables in your template. Sample file can be found in tests directory.

Note that for each device an optional `transform_type` may be specified. Acceptable transform types include:
 - xml
 - hexstring
 - pyparse
 - (unspecified defaults to regex)

Run the config generator with this command:

`python cruise_config_generator.py --voyage_details test_files/sample_devices.yaml --template test_files/cruise_template.jinja --config_output test_files/sample_cruise.yaml`

