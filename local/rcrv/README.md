# Notes for RCRV-specific code

## Prior to running a cruise definition

The file ``settings.py.dist`` in this directory must be copied over to
``settings.py`` prior to running anything that depends on a
CORIOLIXWriter.

## Creating a new cruise definition file

```
  venv/bin/python local/rcrv/build_cruise_definition.py \
    --template local/rcrv/config_template.yaml \
    --host_path http://157.245.173.52:8000/api/ \
    --destination /opt/openrvdas/local/rcrv/cruise.yaml \
    -v
```

The script will read templates and variables from
``local/rcrv/config_template.yaml`` to figure out what configs and
modes to create.

## Creating a new cruise definition whenever anything changes

If you wish the script to periodically check the CORIOLIX database and
generate a new cruise definition when it detects changes or when the
``config_template.yaml`` file changes, add the ``--interval``
argument, e.g. ``--interval 10`` to check every ten seconds:

```
  venv/bin/python local/rcrv/build_cruise_definition.py \
    --template local/rcrv/config_template.yaml \
    --host_path http://157.245.173.52:8000/api/ \
    --destination /opt/openrvdas/local/rcrv/cruise.yaml \
    --interval 10 \
    -v
```

## Updating via HTTP call

If you wish to be able to generate/update the cruise definition via an
http call, you should run ``setup.sh`` in this directory after
OpenRVDAS has been fully installed and set up. This will allow you to
trigger scrupt update via a call to supervisord's web interface:

```
wget -O - 'http://localhost:9001/index.html?processname=update_cruise_definition&action=start' > /dev/null
```


