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
from django.contrib.auth import views as auth_views

from django.conf import settings
from django.conf.urls.static import static

from . import views
from django.views.generic import TemplateView

urlpatterns = [
  path('admin/', admin.site.urls),
  path('login/', auth_views.login, name='login'),
  path('logout/', auth_views.logout,
      {'next_page': '../'}, name='logout'),

  # "path" is /<int:log_level>/<str:cruise_id>/<str:source>/ where any
  # or all fields may be empty
  path('server_messages/<path:path>', views.server_messages,
       name='server_messages'),

  path('edit_config/<str:logger_id>',
       views.edit_config, name='edit_config'),

  path('widget/<str:field_list>', views.widget, name='widget'),
  path('widget/', views.widget, name='widget'),

  path('', views.index, name='index'),
  #path('cruise/', views.index, name='index'),
  #path('cruise/<str:cruise_id>', views.index, name='index'),

  path('demo/', TemplateView.as_view(template_name='widgets/demo.html'),
       name='demo'),
  path('demo/', TemplateView.as_view(template_name='widgets/demo.html'),
       name='demo'),
  path('demo/', TemplateView.as_view(template_name='widgets/demo.html'),
       name='demo'),
  #path('demo/', include('widgets.urls')),
]  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
