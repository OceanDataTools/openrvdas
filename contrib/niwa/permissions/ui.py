from django.db import IntegrityError, models
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from django.contrib import admin


class GlobalPermissionManager(models.Manager):
    def get_queryset(self):
        return (
            super(GlobalPermissionManager, self)
            .get_queryset()
            .filter(content_type__model="global_permission")
        )


class GlobalPermission(Permission):
    """A global permission, not attached to a model"""
    app_label = "django_gui"
    objects = GlobalPermissionManager()

    class Meta:
        proxy = True
        verbose_name = "Global Permission"
        app_label = "django_gui"

    def save(self, *args, **kwargs):
        ct, created = ContentType.objects.get_or_create(
            model=self._meta.verbose_name,
            app_label=self._meta.app_label,
        )
        self.content_type = ct
        super(GlobalPermission, self).save(*args)


class GlobalPermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "codename")
    exclude = ("content_type",)

# used to create the django permission group
ADMIN_UI_PERMISSIONS = [
    "manage_cruise",
    "manage_loggers",
    "manage_udp",
    "view_grafana",
    "view_home",
    "view_native"
]

VIEW_ONLY_PERMISSIONS = [
    "view_home",
    "view_grafana"
]

def add_global_permissions():

    default_ui_permissions = [
        {"name": "UI | View Home", "codename": "view_home"},
        {"name": "UI | Manage Cruise Config", "codename": "manage_cruise"},
        {"name": "UI | Manage Loggers", "codename": "manage_loggers"},
        {"name": "UI | Manage UDP Subscriptions", "codename": "manage_udp"},
        {"name": "UI | View Native UI", "codename": "view_native"},
        {"name": "UI | View Grafana", "codename": "view_grafana"},
    ]

    # make sure these permissions always get added, they will show in the regular Permission table
    for permission in default_ui_permissions:

        try:
            GlobalPermission.objects.create(name=permission["name"], codename=permission["codename"])

        except IntegrityError as e:
            # ignore if already exists
            pass