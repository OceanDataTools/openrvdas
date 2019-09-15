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

  path('server_messages', views.server_messages, name='server_messages'),
  path('server_messages/<int:log_level>', views.server_messages,
       name='server_messages'),

  path('edit_config/<str:logger_id>',
       views.edit_config, name='edit_config'),

  # Display html pages at '/display' URL
  path('display/', views.display, name='display'),
  path('display/<path:page_path>', views.display, name='display'),

  # Some hacks so that the display pages can find their JS and CSS
  path('css/<path:css_path>', views.css, name='css'),
  path('js/<path:js_path>', views.js, name='js'),

  path('widget/<str:field_list>', views.widget, name='widget'),
  path('widget/', views.widget, name='widget'),

  path('', views.index, name='index'),
]  + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

