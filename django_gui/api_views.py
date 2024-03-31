#DJANGO CORE Models
from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets,  status, views
from rest_framework.response import Response
from django.http import Http404
from django.shortcuts import get_object_or_404

#RVDAS Models + Serializers
from django_gui.models import Cruise, Logger
from django_gui.serializers import CruiseSerializer, LoggerSerializer

# class CruiseListViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint that allows Cruise to be viewed or edited.
#     """
#     queryset = Cruise.objects.all().order_by('-id')
#     
#     permission_classes = [permissions.IsAuthenticated]


class CruiseDetailView(viewsets.ModelViewSet):
    """
    API endpoint that allows updating and deleting a Model instance.
    """
    serializer_class = CruiseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        queryset = Cruise.objects.all().order_by('-id')
        self.queryset = queryset
        serializer = CruiseSerializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None):
        queryset = Cruise.objects.all()
        cruise = get_object_or_404(queryset, pk=pk)
        serializer = CruiseSerializer(cruise)
        return Response(serializer.data)
    
    def create(self, request):
        serializer = CruiseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, pk=None):
        cruise = Cruise.objects.get(pk=pk)
        serializer = CruiseSerializer(cruise, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def partial_update(self, request, pk=None):
        cruise = Cruise.objects.get(pk=pk)
        serializer = CruiseSerializer(cruise, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, pk=None):
        try:
            cruise = Cruise.objects.get(pk=pk)
        except Cruise.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        cruise.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoggerViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Logger to be viewed or edited.
    """
    queryset = Logger.objects.all().order_by('-id')
    serializer_class = LoggerSerializer
    permission_classes = [permissions.IsAuthenticated]