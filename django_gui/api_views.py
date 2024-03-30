#DJANGO CORE Models
from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets,  status, views
from rest_framework.response import Response
from django.http import Http404

#RVDAS Models + Serializers
from django_gui.models import Cruise, Logger
from django_gui.serializers import CruiseSerializer, LoggerSerializer

# class CruiseListViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint that allows Cruise to be viewed or edited.
#     """
#     queryset = Cruise.objects.all().order_by('-id')
#     serializer_class = CruiseSerializer
#     permission_classes = [permissions.IsAuthenticated]


class CruiseDetailView(viewsets.ModelViewSet):
    """
    API endpoint that allows updating and deleting a specific MyModel instance.
    """
    queryset = Cruise.objects.all().order_by('-id')
    serializer_class = CruiseSerializer

    def get_object(self, pk):
        try:
            return Cruise.objects.get(pk=pk)
        except Cruise.DoesNotExist:
            raise Http404

    def get(self, request, pk, format=None):
        instance = self.get_object(pk)
        serializer = CruiseSerializer(instance)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        instance = self.get_object(pk)
        serializer = CruiseSerializer(instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        instance = self.get_object(pk)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class LoggerViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Logger to be viewed or edited.
    """
    queryset = Logger.objects.all().order_by('-id')
    serializer_class = LoggerSerializer
    permission_classes = [permissions.IsAuthenticated]