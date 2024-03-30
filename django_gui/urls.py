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

from django.conf import settings
from django.conf.urls.static import static
from rest_framework import routers
from . import views
from . import api_views

##
## API ROUTER CONFIG
##
router = routers.DefaultRouter()
# router.register(r'cruise_list', api_views.CruiseListViewSet)
router.register(r'loggers', api_views.LoggerViewSet)
router.register('cruise', api_views.CruiseDetailView, basename='cruise')

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
    #API Views
    path('api/', include(router.urls)),
    path('api/', include('rest_framework.urls', namespace='rest_framework')),
  


] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


