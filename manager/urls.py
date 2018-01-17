from django.urls import path

from . import views

urlpatterns = [
  path('load_config', views.load_config, name='load_config'),
  path('edit_config/<str:config_id>', views.edit_config, name='edit_config'),
  path('', views.index, name='index'),
]
