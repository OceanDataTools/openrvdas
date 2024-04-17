"""gui URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView


    
from rest_framework import routers

from django.conf import settings
from django.conf.urls.static import static
from . import views
from . import api_views



urlpatterns = [
    
    path('', views.index, name='index'),
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    # path('login/', auth_views.login, name='login'),
    # path('logout/', auth_views.logout,
    #    {'next_page': '../'}, name='logout'),

    path('login/', views.login_user, name='login_user'),

    path('change_mode/',
         views.change_mode, name='change_mode'),
    path('edit_config/<str:logger_id>',
         views.edit_config, name='edit_config'),
    path('choose_file/', views.choose_file, name='choose_file'),

    path('widget/<str:field_list>', views.widget, name='widget'),
    path('widget/', views.widget, name='widget'),

    path('fields/', views.fields, name='fields'),
    #
    #API DRF Views     
    #
    path('api/', include('rest_framework.urls', namespace='rest_framework')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/obtain-auth-token/', api_views.CustomAuthToken.as_view(), name="obtain-auth-token"),
    path('api/', api_views.api_root),    
    path('api/cruise-configuration/', api_views.CruiseConfigurationAPIView.as_view(), name='cruise-configuration'),
    path('api/select-cruise-mode/', api_views.CruiseSelectModeAPIView.as_view(), name='select-cruise-mode'),
    path('api/reload-current-configuration/', api_views.CruiseReloadCurrentConfigurationAPIView.as_view(), name='reload-current-configuration'),
    path('api/delete-configuration/', api_views.CruiseDeleteConfigurationAPIView.as_view(), name='delete-configuration'),
    path('api/edit-logger-config/', api_views.EditLoggerConfigAPIView.as_view(), name='edit-logger-config'),
    path('api/load-configuration-file/', api_views.LoadConfigurationFileAPIView.as_view(), name='load-configuration-file')


] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


