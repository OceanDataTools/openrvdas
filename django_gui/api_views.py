#DJANGO CORE Models
from rest_framework.response import Response
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
        'reload-current-configuration': reverse('reload-current-configuration', request=request, format=format)
        
     
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

class DeleteCruiseAPIView(APIView):
    """
    API endpoint to delete a cruise.

    Request Payload:
    POST
    {
        "delete_cruise": true,
        "cruise_id": 123
    }

    Response Payload:
    {
        "status": "cruise deleted"
    }
    
    """
    authentication_classes = [authentication.BasicAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]
    def post(self, request):
        api = _get_api()
        
        log_request(request, 'delete_cruise')

        # Are they deleting a cruise?(!)
        if 'delete_cruise' in request.data:
            logging.info('deleting cruise')
            api.delete_cruise()
            logging.info('cruise deleted')
            return Response({'status': 'cruise deleted'}, 200)
        
        return Response({'status': 'Invalid Request'},400)
    
    def get(self, request):
        try:        
            api = _get_api()
            configuration = api.get_configuration()
            data = {}
            data['cruise_id'] = configuration.get('id', 'Cruise')
        except (ValueError, AttributeError):
            logging.info('No configuration loaded')
            data = {'cruise': 'no cruise loaded'}

        return Response({'status': 'ok', "data": data}, 200)
    
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
        log_request(request, 'get_configuration')        
        template_vars = _get_cruise_config()    
        return Response({'status': 'ok', "configuration": template_vars}, 200)




    

#       cruise.get
#           cruise.get_modes()
#           cruise.get_active_modes()
#       cruise.post
#           cruise.select_mode(mode_name)

#
#       logger.post
#           logger.edit_config(logger_id)
#           logger.new_config(logger_id)
#           logger.update_config(logger_id, config)
#                set_active_logger_config

#   Note, refer to line #211 in views.py
#       logger.get_logger_info()
#           logger.get_active_mode()
#           logger.config_options()
#           logger.default_config()
#           logger.current_config()


#       lost.post
#           load.load_configuration(selection,config_data as json)
#               this needs to be implemented pretty close to the existing code
#               views.py 227 with creating files system locations like the main ui view. 
#               
#               What is complicated here is the free form YAML config. 
#               Especially when things get big.
#               And being able to define a 'selection'
#               No need to display anything here.
#               API Response should be the loaded config.
#

# Websockets + # Streaming data api. 


# widget api - not sure if this needs an api.









