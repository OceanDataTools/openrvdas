import json
import re
import traceback
import yaml

from rest_framework import authentication, serializers
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from django.urls import path
from django_gui.views import log_request
from django_gui.models import Logger, LoggerConfig
from logger.utils.read_config import parse

from contrib.niwa.shared_methods.loggers import (
    add_logger_without_cruise,
    remove_unused_config,
    save_logger_config,
)


def get_niwa_paths():
    return [
        path(
            "persistent-loggers/<str:logger_name>",
            PersistentLoggerAPIView.as_view(),
            name="get-persistent-loggers",
        ),
        path(
            "yaml-file-content/",
            LoadYamlFileContentAPIView.as_view(),
            name="yaml-file-content",
        ),
        path(
            "save-yaml-file-content/",
            SaveYamlFileContentAPIView.as_view(),
            name="save-yaml-file-content",
        ),
    ]

def get_niwa_schema(request, format=None):
    return {
        "persistent-loggers": reverse(
            "persistent-loggers", request=request, format=format
        ),
        "yaml-file-content": reverse(
            "yaml-file-content", request=request, format=format
        ),
        "save-yaml-file-content": reverse(
            "save-yaml-file-content", request=request, format=format
        ),
    }

class PersistentLoggerSerializer(serializers.Serializer):
    persistent_loggers = serializers.DictField(required=False)
    # TODO LW: add in schema for POST

class PersistentLoggerAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PersistentLoggerSerializer

    def get(self, request, logger_name):
        log_request(request, "get_persistent_loggers")
        logger_data = []
        for logger in Logger.objects.filter(cruise=None).all():
            configs = LoggerConfig.objects.filter(logger_id=logger.id).order_by('logger_id').values_list('config_json', flat=True)

            config_yaml_objs = []
            for row in configs:
                config_obj = json.loads(row)
                named_config_obj = {}
                named_config_obj[config_obj.get("name", "")] = config_obj
                config_yaml = yaml.dump(named_config_obj, indent=2)
                config_yaml_objs.append(config_yaml)
            
            combined_config = "\n".join(config_yaml_objs)

            logger_data.append([logger.id, logger.name, combined_config])

        response = {
            "status": "ok",
            "persistent_loggers": logger_data,
        }

        return Response(response, 200)

    def post(self, request, logger_name):
        request_body = json.loads(request.body)
        logger_id=request_body.get("logger_id", None)
        config_to_set = parse(request_body["logger_config"])
        
        response = {}

        try:
            if logger_id:
                existing_logger = Logger.objects.filter(id=logger_id).first()
                existing_logger.name = logger_name
                save_logger_config(existing_logger, config_to_set)
                existing_logger.save()

                remove_unused_config(logger_id, [name for name in config_to_set])

                response["message"] = f"Logger {existing_logger.name} updated"
            else:
                new_logger = add_logger_without_cruise(logger_name, config_to_set)
                response["message"] = f"Logger {new_logger.name} created"
            
            response["status"] = "ok"
            return Response(response, 200)
        
        except Exception as e:
            response["status"] = "error"
            response["message"] = f"Error saving logger: {str(e)}"
            response["errors"] = [
                "".join(traceback.TracebackException.from_exception(e).format())
            ]
            return Response(response, 500)

class YamlFileContentSerializer(serializers.Serializer):
    content = serializers.FileField(required=True)
    # TODO LW: add in schema for POST


class LoadYamlFileContentAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = YamlFileContentSerializer

    def post(self, request):
        log_request(request, "yaml_file_content")

        filepath = json.loads(request.body).get("filepath", None)
        if filepath is None:
            response = {
                "status": "error",
                "errors": ["No file specified"]
            }
            return Response(response, 400)
        elif re.search("\.yaml$", filepath):
            response = {
                "status": "ok", 
                "content": open(filepath, "r").read()
            }
            return Response(response, 200)
        else:
            response = {
                "status": "error", 
                "errors": ["Invalid file"]
            }
            return Response(response, 400)

class SaveYamlFileContentAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = YamlFileContentSerializer

    def post(self, request):
        log_request(request, "save_yaml_file_content")

        filepath = request.POST.get("filepath")
        content = request.POST.get("content")

        save_errors = []

        try:
            file = open(filepath, "w")
            file.write(content)

            response = {
                "status": "ok",
                "message": f"File updated ({filepath})",
                "content": content,
            }
            return Response(response, 200)

        except Exception as e:
            save_errors.append('Error saving file "%s": %s' % (filepath, str(e)))

            response = {
                "status": "error",
                "message": "There was a problem saving your changes",
                "content": None,
                "errors": save_errors,
            }
            return Response(response, 500)