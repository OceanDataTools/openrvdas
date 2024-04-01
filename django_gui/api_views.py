#DJANGO CORE Models
from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets,  status, views
from rest_framework.response import Response
from django.http import Http404
from django.shortcuts import get_object_or_404

#RVDAS Models + Serializers

#       index.post
#           index.delete_cruise
#           index.select_mode
#           index.reload_current_config

#       index.get
#           index.get_configuration

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









