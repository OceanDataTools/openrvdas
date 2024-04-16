#DJANGO CORE Models
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView
from .django_server_api import DjangoServerAPI
from django_gui.settings import FILECHOOSER_DIRS
from django_gui.settings import WEBSOCKET_DATA_SERVER
import logging
from rest_framework import authentication
from .views import log_request
from rest_framework.decorators import api_view
from rest_framework.reverse import reverse
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
import json
import yaml
import os
from os.path import dirname, realpath, isfile, isdir, abspath

from rest_framework.settings import api_settings
# Read in JSON with comments
from logger.utils.read_config import parse, read_config  # noqa: E402

#RVDAS Models + Serializers


# In DRF, request data is typically accessed through request.data, 
# which is a parsed representation of the request body. This is 
# designed to work with various content types like JSON, form 
# data, etc. In Django, request.POST is used for form data, and 
# request.body contains the raw request payload.


#Interacting with the Django DB via its API class 
#As per the standard view.
api = None

@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'login': reverse('rest_framework:login', request=request, format=format),
        'logout': reverse('rest_framework:logout', request=request, format=format),
        'obtain-auth-token': reverse('obtain-auth-token', request=request, format=format),
        'cruise-configuration': reverse('cruise-configuration', request=request, format=format),
        'delete-cruise': reverse('delete-cruise', request=request, format=format),
        'select-cruise-mode': reverse('select-cruise-mode', request=request, format=format),
        'reload-current-configuration': reverse('reload-current-configuration', request=request, format=format),
        'edit-logger-config': reverse('edit-logger-config', request=request, format=format),
        'load-configuration-file': reverse('load-configuration-file', request=request, format=format),
     
    })

def _get_api():
    
    global api
    if api is None:
        api = DjangoServerAPI()
        logging.info("API initialized")

    return api

class CustomAuthToken(ObtainAuthToken):

    renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
        
    
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.pk,
            'create': created,
        })

#
#
# CRUISE ACTIONS
#
#

#       index.get
#           index.get_configuration
class CruiseConfigurationAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):        
        log_request(request, 'get_configuration')        
        template_vars = _get_cruise_config()    
        return Response({'status': 'ok', "configuration": template_vars}, 200)
  
def _get_cruise_config():

    errors = []
    
    template_vars = {
        'websocket_server': WEBSOCKET_DATA_SERVER,
        'errors': {'django': errors},
        }
    
    try:        
        api = _get_api()
        configuration = api.get_configuration()
        template_vars['cruise_id'] = configuration.get('id', 'Cruise')
        template_vars['filename'] = configuration.get('config_filename', '-none-')
        template_vars['loggers'] = api.get_loggers()
        template_vars['modes'] = api.get_modes()
        template_vars['active_mode'] = api.get_active_mode()
        template_vars['errors'] = errors
    except (ValueError, AttributeError):
            logging.info('No configuration loaded')
    
    return template_vars

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

    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api = _get_api()
        log_request(request, 'select_mode')

        # Are they deleting a cruise?(!)
        if 'select_mode' in request.data:
            try:
                new_mode_name = request.data['select_mode']
                logging.info('switching to mode "%s"', new_mode_name)
                api.set_active_mode(new_mode_name)
                return Response({'status': f'Cruise mode set: {new_mode_name}'}, 200)

            except ValueError as e:
                logging.warning('Error trying to set mode to "%s": %s',
                                new_mode_name, str(e))
                return Response({'status': f'Invalid Request. Error trying to set mode to {new_mode_name}'},400)        
        return Response({'status': 'Invalid Request'},400)
    
    def get(self, request):
        try:        
            api = _get_api()            
            data = {}
            data['modes'] = api.get_modes()
            data['active_mode'] = api.get_active_mode()
        except (ValueError, AttributeError):
            logging.info('No configuration loaded')
            data = {'modes': 'no cruise loaded'}

        return Response({'status': 'ok', "data": data}, 200)

class CruiseReloadCurrentConfigurationAPIView(APIView):
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        api = _get_api()
        log_request(request, "reload current cruise configuration")

        if 'reload' in request.data:            
            logging.info('reloading current configuration file')
            try:
                cruise = api.get_configuration()
                filename = cruise['config_filename']
                # Load the file to memory and parse to a dict. Add the name
                # of the file we've just loaded to the dict.
                config = read_config(filename)
                if 'cruise' in config:
                    config['cruise']['config_filename'] = filename
                api.load_configuration(config)

                return Response({'status': 'Current config reloaded'},200)
            except ValueError as e:
                logging.warning('Error reloading current configuration: %s', str(e))
    
        return Response({'status': 'Invalid Request'},400)
    
    def get(self, request):        
        log_request(request, 'reload_configuration')        
        template_vars = _get_cruise_config()    
        return Response({'status': 'ok', "configuration": template_vars}, 200)

class EditLoggerConfigAPIView(APIView):
    """
    API endpoint for editing logger configurations.

    This endpoint supports both POST and GET requests.
    POST request allows updating logger configurations.
    GET request retrieves the list of loggers.

    Authentication:
    - BasicAuthentication
    - TokenAuthentication

    Permissions:
    - IsAuthenticated

    """

    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Update logger configuration.

        POST Parameters:
        - logger_id: The ID of the logger to be updated.
        - select_config: The new configuration to be set.
        {
        "update": true,
        "logger_id": "<logger_id>",
        "select_config": "<config_id>"
        }

        Returns:
        - Response with status and message.

        """
        api = _get_api()
        if 'update' in request.data:
            logger_id = request.data['logger_id']
            # First things first: log the request
            log_request(request, '%s edit_config' % logger_id)

            # Now figure out what they selected
            new_config = request.data['select_config']
            logging.warning('selected config: %s', new_config)
            api.set_active_logger_config(logger_id, new_config)
            
            return Response({'status': f'Logger {logger_id} updated.'}, status=200)
        return Response({'status': 'Invalid Request'}, status=400)
    
    def get(self, request):
        """
        Retrieve list of loggers.

        Returns:
        - Response with status and list of loggers.

        """
        api = _get_api()
        log_request(request, 'get_loggers')               
        loggers = None
        try:
            loggers = api.get_loggers()
            msg = None
        except Exception as e:     
            msg = str(e)
        
        return Response({'status': 'ok', "loggers": loggers, 'msg': msg}, status=200)

class LoadConfigurationFileAPIView(APIView):
    """
        Load Configuration File

        Get:
            returns a json object containing a tree of files in your files folder.
        
        POST:
        {
            
            'target_file': '<a file path string>'

        }

        Returns:
        - Response with status and message.

    """
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]



    def get(self, request):
        # list all files in a tree
        files = self._list_files_in_folder()
        return Response({'status': 'ok', "files": files}, status=200)
        
    def _list_files_in_folder(self):

        config_files = {}
        for file_dir in FILECHOOSER_DIRS:
            folder_dict = {}
            for root, dirs, files in os.walk(file_dir):
                current_dir = os.path.relpath(root, file_dir)
                if current_dir == '.':
                    current_dir = ''
                    continue
                current_dir_dict = folder_dict
                for dir_name in current_dir.split(os.path.sep):
                    current_dir_dict = current_dir_dict.setdefault(dir_name, {})
                current_dir_dict.update({file_name: os.path.join(root, file_name) for file_name in files})
            
            config_files[file_dir] = folder_dict

        return config_files
        


    def post(self, request):
        api = _get_api()
        if 'target_file' in request.data:
            #try to load it.
            load_errors = []
            target_file = request.data.get('target_file', None)
            if target_file is None:
                return Response({'status': f'File not found. {target_file}'},404)
            try:
                with open(target_file, 'r') as config_file:                    
                    configuration = parse(config_file.read())                    
                    if 'cruise' in configuration:
                        configuration['cruise']['config_filename'] = target_file                    
                    # Load the config and set to the default mode
                    api.load_configuration(configuration)
                    default_mode = api.get_default_mode()
                    if default_mode:
                        api.set_active_mode(default_mode)                    
                    return Response({'status': f'target_file loaded {target_file}'}, 200)
                
            except (json.JSONDecodeError, yaml.scanner.ScannerError) as e:                
                load_errors.append('Error loading "%s": %s' % (target_file, str(e)))
            except ValueError as e:                
                load_errors.append(str(e))
            
            return Response({'status': f"Errors loading target file {target_file}", "errors": load_errors}, 400)
            










