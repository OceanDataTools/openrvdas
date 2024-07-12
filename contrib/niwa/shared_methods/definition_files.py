import glob
import logging
from logger.utils import read_config


def parse_definition_files(file_paths, definitions=None):
    # If nothing was passed in, start with base case.
    definitions = definitions or {"devices": {}, "device_types": {}}

    all_definitions = []

    for filespec in file_paths.split(","):
        filenames = glob.glob(filespec)
        if not filenames:
            logging.warning('No files match definition file spec "%s"', filespec)

        for filename in filenames:
            file_output = {
                "filename": filename,
                "definition": {"devices": {}, "device_types": {}},
            }
            definition = file_output["definition"]
            file_definitions = read_config.read_config(filename)

            for key, val in file_definitions.items():
                # If we have a dict of device definitions, copy them into the
                # 'devices' key of our definitions.
                if key == "devices":
                    if not isinstance(val, dict):
                        logging.error(
                            '"devices" values in file %s must be dict. '
                            'Found type "%s"',
                            filename,
                            type(val),
                        )
                        return None

                    for device_name, device_def in val.items():
                        if device_name in definition["devices"]:
                            logging.warning(
                                'Duplicate definition for "%s" found in %s',
                                device_name,
                                filename,
                            )
                        definition["devices"][device_name] = device_def

                # If we have a dict of device_type definitions, copy them into the
                # 'device_types' key of our definitions.
                elif key == "device_types":
                    if not isinstance(val, dict):
                        logging.error(
                            '"device_typess" values in file %s must be dict. '
                            'Found type "%s"',
                            filename,
                            type(val),
                        )
                        return None

                    for device_type_name, device_type_def in val.items():
                        if device_type_name in definition["device_types"]:
                            logging.warning(
                                'Duplicate definition for "%s" found in %s',
                                device_type_name,
                                filename,
                            )
                        definition["device_types"][device_type_name] = device_type_def

                # If we're including other files, recurse inelegantly
                elif key == "includes":
                    if not type(val) in [str, list]:
                        logging.error(
                            '"includes" values in file %s must be either '
                            'a list or a simple string. Found type "%s"',
                            filename,
                            type(val),
                        )
                        return None

                    if isinstance(val, str):
                        val = [val]
                    for filespec in val:
                        new_defs = parse_definition_files(filespec, definition)[0]
                        definition["devices"].update(new_defs.get("devices", {}))
                        definition["device_types"].update(
                            new_defs.get("device_types", {})
                        )

                # If it's not an includes/devices/device_types def, assume
                # it's a (deprecated) top-level device or device_type
                # definition. Try adding it to the right place.
                else:
                    category = val.get("category", None)
                    if category not in ["device", "device_type"]:
                        logging.warning(
                            'Top-level definition "%s" in file %s is not '
                            'category "device" or "device_type". '
                            'Category is "%s" - ignoring',
                            category,
                        )
                        continue
                    if category == "device":
                        if key in definition["devices"]:
                            logging.warning(
                                'Duplicate definition for "%s" found in %s',
                                key,
                                filename,
                            )
                        definition["devices"][key] = val
                    else:
                        if key in definition["device_types"]:
                            logging.warning(
                                'Duplicate definition for "%s" found in %s',
                                key,
                                filename,
                            )
                        definition["device_types"][key] = val

                all_definitions.append(file_output)
    # Finally, return the accumulated definitions
    return all_definitions