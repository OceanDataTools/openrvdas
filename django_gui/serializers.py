from django.contrib.auth.models import Group, User
from rest_framework import serializers
from django_gui.models import Cruise, Logger


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'groups']


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

class CruiseSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Cruise
        fields = ["id", "start", "end", "config_filename","config_text","loaded_time", "active_mode_id", "default_mode" ]

class LoggerSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Logger
        fields = ["id", "name", "config_id", "cruise_id"]
        