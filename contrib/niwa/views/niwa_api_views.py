import glob
import json
import re
import traceback
from django.conf import settings
import yaml

from ipware import get_client_ip

from rest_framework import authentication, serializers
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from django.urls import path
from django.contrib.auth.models import Group, Permission, User
from django.db import IntegrityError
from django.db.models import Q
from contrib.niwa.permissions.ui import ADMIN_UI_PERMISSIONS, VIEW_ONLY_PERMISSIONS, add_global_permissions
from django_gui.django_server_api import DjangoServerAPI
from django_gui.views import log_request
from django_gui.models import Logger, LoggerConfig, UDPSubscription
from logger.utils.read_config import parse, read_config

from contrib.niwa.shared_methods.loggers import (
    add_logger_without_cruise,
    get_udp_subscription_ports,
    remove_unused_config,
    save_logger_config,
)



class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication to allow API calls from logger processes using an API_KEY in settings.py 
    """
    def authenticate(self, request):
        given_api_key = request.headers.get("authorization")
        if not given_api_key:
            return None

        if given_api_key == settings.API_KEY:
            return (User(username="api", password="api"), None)
        else:
            raise AuthenticationFailed("Invalid API Key")



api = None
def _get_api():
    global api
    if api is None:
        api = DjangoServerAPI()

    return api


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
        path(
            "create-permissions/",
            CreatePermissionsAPIView.as_view(),
            name="create-permissions",
        ),
        path(
            "create-permission-groups/",
            CreatePermissionGroupsAPIView.as_view(),
            name="create-permission-groups",
        ),
        path(
            "load-persistent-loggers/",
            LoadPersistentLoggersAPIView.as_view(),
            name="load-persistent-loggers",
        ),
        path(
            "get-client-ip/",
            ClientIPAPIView.as_view(),
            name="get-client-ip",
        ),
        path(
            "get-udp-subscriptions-by-ip/<str:ip_address>",
            GetUDPSubscriptionsByIPAPIView.as_view(),
            name="get-udp-subscriptions",
        ),
        path(
            "get-udp-subscriptions-by-logger-id/<int:logger_id>",
            GetUDPSubscriptionsByLoggerIdAPIView.as_view(),
            name="get-udp-subscription-by-logger",
        ),
        path(
            "update-udp-subscriptions/",
            UpdateUDPSubscriptionsAPIView.as_view(),
            name="update-udp-subscriptions",
        ),
        path(
            "get-logger-id-by-name/<str:logger_name>",
            GetLoggerIdAPIView.as_view(),
            name="get-logger-id",
        ),
    ]

def get_niwa_schema(request, format=None):
    return {
        "persistent-loggers": reverse(
            "persistent-loggers", request=request, format=format
        ),
        "load-persistent-loggers": reverse(
            "load-persistent-loggers", request=request, format=format
        ),
        "yaml-file-content": reverse(
            "yaml-file-content", request=request, format=format
        ),
        "save-yaml-file-content": reverse(
            "save-yaml-file-content", request=request, format=format
        ),
        "create-permissions": reverse(
            "create-permissions", request=request, format=format
        ),
        "create-permission-groups": reverse(
            "create-permission-groups", request=request, format=format
        ),
        "get-client-ip": reverse("get-client-ip", request=request, format=format),
        "get-udp-subscriptions-by-ip": reverse(
            "get-udp-subscriptions-by-ip", request=request, format=format
        ),
        "get-udp-subscriptions-by-logger-id": reverse(
            "get-udp-subscriptions-by-logger", request=request, format=format
        ),
        "update-udp-subscriptions": reverse(
            "update-udp-subscriptions", request=request, format=format
        ),
        "get-logger-id-by-name": reverse(
            "get-logger-id", request=request, format=format
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


class ClientIPSerializer(serializers.Serializer):
    ip_address = serializers.CharField()


class ClientIPAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ClientIPSerializer

    def get(self, request):
        try:
            client_ip, is_routertable = get_client_ip(request)

            return Response({"status": "ok", "ip_address": client_ip}, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)


class LoggerIdSerializer(serializers.Serializer):
    logger_id = serializers.CharField()


class GetLoggerIdAPIView(APIView):
    """
    API endpoint used by 'udp_subscription_writer' to know which logger is running
    """

    authentication_classes = [
        authentication.BasicAuthentication,
        TokenAuthentication,
        APIKeyAuthentication,
    ]
    permission_classes = [IsAuthenticated]
    serializer_class = LoggerIdSerializer

    def get(self, request, logger_name):
        try:
            logger_id = Logger.objects.filter(name=logger_name).first().id
            return Response({"status": "ok", "logger_id": logger_id}, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)
        

class UDPSubscriptionSerializer(serializers.Serializer):
    ip_address = serializers.CharField()


class GetUDPSubscriptionsByIPAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = UDPSubscriptionSerializer

    def get(self, request, ip_address):

        if not request.user.has_perm("django_gui.manage_udp"):
            return Response(
                {"status": "error", "message": "Missing UDP permission"}, 401
            )
        
        try:
            cruise_data = _get_api().get_configuration()

            rows = []
            if cruise_data:
                for logger in Logger.objects.filter(Q(cruise_id=cruise_data["id"]) | Q(cruise_id=None)).order_by("name"):
                    is_subscribed = logger.udpsubscription_set.filter(ip_address=ip_address).exists()
                    port_numbers = get_udp_subscription_ports(logger.config.config_json)
                    rows.append([logger.id, logger.name, ", ".join(port_numbers), is_subscribed])

            response = {
                "status": "ok",
                "rows": rows,
            }

            return Response(response, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)

class GetUDPSubscriptionsByLoggerIdAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication, APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = UDPSubscriptionSerializer

    def get(self, request, logger_id):
        
        try:
            subscribed_ip_addresses = []

            for subscription in UDPSubscription.objects.filter(
                logger_id=logger_id
            ).all():           
                subscribed_ip_addresses.append(subscription.ip_address)

            response = {
                "status": "ok",
                "ip_addresses": subscribed_ip_addresses,
            }

            return Response(response, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)


class UpdateUDPSubscriptionsAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = UDPSubscriptionSerializer

    def post(self, request):

        if not request.user.has_perm("django_gui.manage_udp"):
            return Response(
                {"status": "error", "message": "Missing UDP permission"}, 401
            )

        try:
            data = json.loads(request.body)
            ip_address = data.get("ip", None)
            changes = data.get("changes", None)

            if not ip_address:
                return Response(
                    {
                        "status": "error",
                        "message": "Changes were not saved, no IP address given",
                        "errors": ["No IP"],
                    }, 400
                )      

            if not changes:
                return Response(
                    {
                        "status": "ok",
                        "message": "No changes to save",
                        "errors": ["No changes"],
                    }, 200
                )

            to_insert = []
            to_delete = []

            for (logger_id, subscribe) in changes.items():
                if subscribe:
                    to_insert.append(UDPSubscription(logger_id=logger_id, ip_address=ip_address))
                else:
                    to_delete.append(logger_id)

            UDPSubscription.objects.bulk_create(to_insert)
            UDPSubscription.objects.filter(ip_address=ip_address).filter(logger_id__in=to_delete).delete()

            response = {
                "status": "ok",
                "message": ["UDP subscriptions updated.", f"{len(to_insert)} added, {len(to_delete)} removed."],
            }

            return Response(response, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)


### Admin Shortcuts

class BlankSerializer(serializers.Serializer):
    pass


class CreatePermissionsAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]
    serializer_class = BlankSerializer


    def get(self, request):
        try:
            add_global_permissions()

            return Response(
                {"status": "ok", "message": "Permissions created"}, 200
            )

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)


class CreatePermissionGroupsAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]
    serializer_class = BlankSerializer


    def create_group(self, name, permissions):
        try:
            group = Group(name=name)
            group.save()

            for permission in permissions:
                group.permissions.add(permission)

            group.save()
        except IntegrityError:
            pass


    def get(self, request):
        
        default_admin_permissions = Permission.objects.filter(
            codename__in=ADMIN_UI_PERMISSIONS
        )

        default_viewer_permissions = Permission.objects.filter(
            codename__in=VIEW_ONLY_PERMISSIONS
        )

        try:
            self.create_group(name="Admin", permissions=default_admin_permissions)
            self.create_group(name="Viewer", permissions=default_viewer_permissions)

            return Response({"status": "ok", "message": "Permission groups created"}, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)


class LoadPersistentLoggersAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]
    serializer_class = BlankSerializer

    def get(self, request):
        try:
            relative_file_location = "local/logger_configs/*.yaml"
            file_paths = glob.glob(relative_file_location)

            loggers_added = []
            loggers_skipped = []

            for logger_file in file_paths:           
                logger_name = logger_file.split("/")[-1].split(".")[0]
                logger_config = read_config(logger_file)

                if not Logger.objects.filter(name=logger_name).exists():
                    new_logger = add_logger_without_cruise(logger_name, logger_config)
                    loggers_added.append(new_logger.name)
                else:
                    loggers_skipped.append(logger_name)

            response = {
                "status": "ok",
                "message": f"{', '.join(loggers_added)}{" loaded" if len(loggers_added) else ""}{", " if len(loggers_added) else ""}{', '.join(loggers_skipped)}{" skipped" if len(loggers_skipped) else ""}",
                "loggersAdded": loggers_added,
                "loggersSkipped": loggers_skipped,
                "filePaths": file_paths,
            }

            return Response(response, 200)

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, 500)


####
