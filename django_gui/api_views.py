from .django_server_api import DjangoServerAPI
from django_gui.settings import FILECHOOSER_DIRS
from django_gui.settings import WEBSOCKET_DATA_SERVER

from rest_framework import authentication, serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authentication import TokenAuthentication
from rest_framework.compat import coreapi, coreschema
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.schemas import ManualSchema, coreapi as coreapi_schema
from rest_framework.views import APIView

from .views import log_request

import json
import logging
import yaml
import os
from rest_framework.settings import api_settings
# Read in JSON with comments
from logger.utils.read_config import parse, read_config  # noqa: E402

# RVDAS API Views + Serializers

# In DRF, request data is typically accessed through request.data,
# which is a parsed representation of the request body. This is
# designed to work with various content types like JSON, form
# data, etc. In Django, request.POST is used for form data, and
# request.body contains the raw request payload.

# About the general layout of this file.
# Each API View that features a POST action uses a serializer to wrap those values.

# In each APIView with a post action there is a code block in ther class
#
#  if coreapi_schema.is_enabled():
#        schema = ....
#
# These act as a hint that allows the core django rest framework to generate an API UI for POST requests.

# Interacting with the Django DB via its API class
# As per the standard view.
api = None


@api_view(["GET"])
def api_root(request, format=None):
    """
    RVDAS REST API Endpoints.

    These are an authenticated set of urls.
    You need to to login to use them via the APi ui.
    For calling them via curl or requests. You need to pass header authenticiation.
    Use token auth, it's simpler.
    But basic auth is supported.
    https://www.django-rest-framework.org/api-guide/authentication/

    Such as:
    curl -H "Authorization: Token <a token string>" http://127.0.0.1:8000/api/cruise-configuration/**

    Via a browser you can use this interface with
    http://127.0.0.1:8000/api/cruise-configuration/?format=json

    There are also the drf-spectacular endpoints for swagger files and integration at
    /api/scheam/ < to fetch the yaml schema
    /api/schema/docs to use the openai version of this interface.

    """
    return Response(
        {
            # flake8: noqa E501
            "login": reverse("rest_framework:login", request=request, format=format),
            "logout": reverse("rest_framework:logout", request=request, format=format),
            "obtain-auth-token": reverse("obtain-auth-token", request=request, format=format),
            "cruise-configuration": reverse("cruise-configuration", request=request, format=format),
            "select-cruise-mode": reverse("select-cruise-mode", request=request, format=format),
            "reload-current-configuration": reverse("reload-current-configuration", request=request, format=format),
            "delete-configuration": reverse("delete-configuration", request=request, format=format),
            "edit-logger-config": reverse("edit-logger-config", request=request, format=format),
            "load-configuration-file": reverse("load-configuration-file", request=request, format=format),
        }
    )


def _get_api():

    global api
    if api is None:
        api = DjangoServerAPI()
        logging.info("API initialized")

    return api


class CustomAuthToken(ObtainAuthToken):

    renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})

        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, created = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user_id": user.pk,
                "create": created,
            }
        )


#
#
# CRUISE LEVEL ACTIONS
#
#


class CruiseConfigurationAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        log_request(request, "get_configuration")
        template_vars = _get_cruise_config()
        return Response({"status": "ok", "configuration": template_vars}, 200)


def _get_cruise_config():

    errors = []

    template_vars = {
        "websocket_server": WEBSOCKET_DATA_SERVER,
        "errors": {"django": errors},
    }

    try:
        api = _get_api()
        configuration = api.get_configuration()
        template_vars["cruise_id"] = configuration.get("id", "Cruise")
        template_vars["filename"] = configuration.get("config_filename", "-none-")
        template_vars["loggers"] = api.get_loggers()
        template_vars["modes"] = api.get_modes()
        template_vars["active_mode"] = api.get_active_mode()
        template_vars["errors"] = errors
    except (ValueError, AttributeError):
        logging.info("No configuration loaded")

    return template_vars


class CruiseSelectModeSerializer(serializers.Serializer):
    select_mode = serializers.CharField(required=True)


class CruiseSelectModeAPIView(APIView):
    """
    API endpoint to Select a Cruise Mode.

    Request Payload:
    POST
    {
        "select_mode": mode_id,
    }

    Response Payload:
    {
        "status": "Cruise mode set: new cruise"
    }
    """

    if coreapi_schema.is_enabled():
        schema = ManualSchema(
            fields=[
                coreapi.Field(
                    name="select_mode",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="select_mode",
                        description="Valid mode_id for configuartion.",
                    ),
                ),
            ],
            encoding="application/json",
        )

    serializer_class = CruiseSelectModeSerializer
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api = _get_api()
        log_request(request, "select_mode")
        serializer = CruiseSelectModeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("select_mode"):
            try:
                new_mode_name = serializer.validated_data["select_mode"]
                logging.info('switching to mode "%s"', new_mode_name)
                api.set_active_mode(new_mode_name)
                return Response({"status": f"Cruise mode set: {new_mode_name}"}, status=200)

            except ValueError as e:
                logging.warning('Error trying to set mode to "%s": %s', new_mode_name, str(e))
                return Response(
                    {"status": f"Invalid Request. Error trying to set mode to {new_mode_name}"},
                    status=400)
        return Response({"status": "Invalid Request"}, status=400)

    def get(self, request):
        try:
            api = _get_api()
            data = {}
            data["modes"] = api.get_modes()
            data["active_mode"] = api.get_active_mode()
        except (ValueError, AttributeError):
            logging.info("No configuration loaded")
            data = {"modes": "no cruise loaded"}

        return Response({"status": "ok", "data": data}, 200)


class CruiseReloadCurrentConfiguartionSerializer(serializers.Serializer):
    # The presence of the value implies the
    reload = serializers.CharField(required=True)


class CruiseReloadCurrentConfigurationAPIView(APIView):
    """
    Reload Current Configuration API

    Request Payload:
    POST
    {
        "reload": true,
    }

    Response Payload:
    {
        "status": "ok",
        "configuration": ...
    }
    """

    if coreapi_schema.is_enabled():
        schema = ManualSchema(
            fields=[
                coreapi.Field(
                    name="reload",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="reload",
                        description="true / false",
                    ),
                ),
            ],
            encoding="application/json",
        )

    serializer_class = CruiseReloadCurrentConfiguartionSerializer
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):

        api = _get_api()
        log_request(request, "reload current cruise configuration")
        serializer = CruiseReloadCurrentConfiguartionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("reload"):
            logging.info("reloading current configuration file")
            try:
                cruise = api.get_configuration()
                filename = cruise["config_filename"]
                # Load the file to memory and parse to a dict. Add the name
                # of the file we've just loaded to the dict.
                config = read_config(filename)
                if "cruise" in config:
                    config["cruise"]["config_filename"] = filename
                api.load_configuration(config)

                return Response({"status": "Current config reloaded"}, 200)
            except Exception as e:
                logging.warning("Error reloading current configuration: %s", str(e))
                return Response({"status": f"Error reloading current configuration: {e}"}, 400)

        return Response({"status": "Invalid Request"}, 400)

    def get(self, request):
        log_request(request, "reload_configuration")
        template_vars = _get_cruise_config()
        return Response({"status": "ok", "configuration": template_vars}, 200)


class CruiseDeleteConfigurationSerializer(serializers.Serializer):
    delete = serializers.CharField(required=True)


class CruiseDeleteConfigurationAPIView(APIView):
    """
    API endpoint for deleting all configurations.
    """

    if coreapi_schema.is_enabled():
        schema = ManualSchema(
            fields=[
                coreapi.Field(
                    name="delete",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="delete",
                        description="id for configuration.",
                    ),
                ),
            ],
            encoding="application/json",
        )

    serializer_class = CruiseDeleteConfigurationSerializer
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # The serializer takes a KV pair. Delete:value that isn't used other than to check it
        # exists. In the future if there is the intent to store more than a single cruise
        # configuration in the db, then this api can be expanded to cater to this.
        api = _get_api()
        log_request(request, "delete_configuration")
        serializer = CruiseDeleteConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("delete"):
            try:
                api.delete_configuration()
                return Response({"status": "Cruise configuration deleted"}, status=200)

            except ValueError as e:
                logging.warning(f"Error trying to delete configuration: {e}")
                return Response(
                    {"status": "Invalid Request. Error trying to delete configuration"}, status=400)
        return Response({"status": "Invalid Request"}, status=400)

    def get(self, request):
        try:
            api = _get_api()
            data = {}
            configuration = api.get_configuration()
            data["cruise_id"] = configuration.get("id", "Cruise")
        except (ValueError, AttributeError):
            logging.info("No configuration loaded")
            data = {"cruise_id": "no cruise loaded"}

        return Response({"status": "ok", "data": data}, 200)


#
#
#
# LOGGER ACTIONS
#
#
#
class EditLoggerConfigSerializer(serializers.Serializer):
    update = serializers.CharField(required=True)
    logger_id = serializers.CharField(required=True)
    config = serializers.CharField(required=True)


class EditLoggerConfigAPIView(APIView):
    """
    API endpoint for editing logger configurations.

    This endpoint supports both POST and GET requests.
    POST request allows updating logger configurations.
    GET request retrieves the list of loggers.

    POST Parameters:
    - update: true
    - logger_id: The ID of the logger to be updated.
    - config: The new configuration to be set.
    {
    "update": "true",
    "logger_id": "<logger_id>",
    "config": "<config_id>"
    }

    Returns:
    - Response with status and message
    """

    if coreapi_schema.is_enabled():
        schema = ManualSchema(
            fields=[
                coreapi.Field(
                    name="update",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="realod",
                        description="true / false",
                    ),
                ),
                coreapi.Field(
                    name="logger_id",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="realod",
                        description="The logger id to update",
                    ),
                ),
                coreapi.Field(
                    name="config",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="realod",
                        description="The logger id to update",
                    ),
                ),
            ],
            encoding="application/json",
        )

    serializer_class = EditLoggerConfigSerializer
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api = _get_api()
        log_request(request, "Edit logger configuration")

        serializer = EditLoggerConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("update"):
            logger_id = serializer.validated_data.get("logger_id")
            log_request(request, "%s edit_config" % logger_id)

            # Figure out what they selected
            new_config = serializer.validated_data.get("config")
            logging.warning("selected config: %s", new_config)
            api.set_active_logger_config(logger_id, new_config)

            return Response({"status": f"Logger {logger_id} updated."}, status=200)

        return Response({"status": "Invalid Request"}, status=400)

    def get(self, request):
        """
        Retrieve list of loggers.

        Returns:
        - Response with status and list of loggers.
        """
        api = _get_api()
        log_request(request, "get_loggers")
        loggers = None
        try:
            loggers = api.get_loggers()
            msg = None
        except Exception as e:
            msg = str(e)

        return Response({"status": "ok", "loggers": loggers, "msg": msg}, status=200)


class LoadConfigurationFileSerializer(serializers.Serializer):
    target_file = serializers.CharField(required=True)


class LoadConfigurationFileAPIView(APIView):
    """
    Load Configuration File

    GET:
        returns a json object containing a tree of files in your files folder.

    POST:
    {

        'target_file': '<a file path string>'

    }

    Returns:
    - Response with status and message.
    """

    if coreapi_schema.is_enabled():
        schema = ManualSchema(
            fields=[
                coreapi.Field(
                    name="target_file",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        title="target_file",
                        description="A path to a file.",
                    ),
                ),
            ],
            encoding="application/json",
        )

    serializer_class = LoadConfigurationFileSerializer
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # list all files in a tree
        files = self._list_files_in_folder()
        return Response({"status": "ok", "files": files}, status=200)

    def _list_files_in_folder(self):
        config_files = {}
        for file_dir in FILECHOOSER_DIRS:
            folder_dict = {}
            for root, dirs, files in os.walk(file_dir):
                current_dir = os.path.relpath(root, file_dir)
                if current_dir == ".":
                    current_dir = ""
                    continue
                current_dir_dict = folder_dict
                for dir_name in current_dir.split(os.path.sep):
                    current_dir_dict = current_dir_dict.setdefault(dir_name, {})
                current_dir_dict.update({file_name: os.path.join(root, file_name)
                                         for file_name in files})

            config_files[file_dir] = folder_dict

        return config_files

    def post(self, request):
        api = _get_api()
        log_request(request, "Load configuration file.")

        serializer = LoadConfigurationFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("target_file"):
            # try to load it.
            load_errors = []
            target_file = serializer.validated_data.get("target_file", None)

            if target_file is None:
                return Response({"status": f"File not found. {target_file}"}, 404)
            try:
                with open(target_file, "r") as config_file:
                    configuration = parse(config_file.read())
                    if "cruise" in configuration:
                        configuration["cruise"]["config_filename"] = target_file
                    # Load the config and set to the default mode
                    api.load_configuration(configuration)
                    default_mode = api.get_default_mode()
                    if default_mode:
                        api.set_active_mode(default_mode)
                    return Response({"status": f"target_file loaded {target_file}"}, 200)

            except (json.JSONDecodeError, yaml.scanner.ScannerError) as e:
                load_errors.append('Error loading "%s": %s' % (target_file, str(e)))
            except ValueError as e:
                load_errors.append(str(e))

            return Response({"status": f"Errors loading target file {target_file}",
                             "errors": load_errors}, 400)
