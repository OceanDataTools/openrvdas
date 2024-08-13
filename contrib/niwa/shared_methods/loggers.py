import json
import logging
import re
from django_gui.models import Logger, LoggerConfig


def add_logger_without_cruise(name, logger_config: dict):
    new_logger = Logger(name=name)
    new_logger.save()

    if logger_config is None:
        raise ValueError("Logger %s has no config declaration" % (name))

    configs = save_logger_config(new_logger, logger_config)
    if new_logger.config is None:
        new_logger.config = configs[0]
        new_logger.save()

    return new_logger


def save_logger_config(logger, logger_config):
    configs = []
    set_current = False
    for config_name in logger_config:
        config_spec = logger_config.get(config_name, None)
        if config_spec is None:
            raise ValueError("Config %s not found" % (config_name))
        logging.debug("Associating config %s with logger %s", config_name, logger.name)
        logging.debug("config_spec: %s", config_spec)

        # A minor hack: fold the config's name into the spec
        if "name" not in config_spec:
            config_spec["name"] = config_name

        existing_config = LoggerConfig.objects.filter(
            logger_id=logger.id, name=config_name
        ).first()

        if existing_config is not None:
            existing_config.config_json = json.dumps(config_spec)
            existing_config.save()
        else:
            config = LoggerConfig(
                name=config_name,
                logger=logger,
                config_json=json.dumps(config_spec),
                current_config=not set_current,
            )
            set_current = True
            config.save()
            configs.append(config)

    return configs


def remove_unused_config(logger_id, config_names):
    number_deleted = (
        LoggerConfig.objects.filter(logger_id=logger_id)
        .exclude(name__in=config_names)
        .delete()
    )
    return number_deleted


def get_udp_subscription_ports(config):
    port_regex = re.compile('UDPSubscriptionWriter.*port":\D*(\d*)', re.MULTILINE)
    matches = port_regex.findall(config)

    return matches
