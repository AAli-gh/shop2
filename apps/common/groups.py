"""Role groups for staff permissions. Run once:
    python manage.py setup_groups
"""
PERMISSIONS = {
    "پشتیبانی": {
        "orders": ["view", "change"],          # view + advance status via transitions
        "accounts": ["view", "change"],
        "common": ["view"],                     # contact messages
        "cart": ["view"],
    },
    "مالی": {
        "orders": ["view", "change"],
        "reps": ["view"],
        "discounts": ["view", "add", "change"],
        "wallet": ["view"],
        "reviews": ["view"],
        "loyalty": ["view"],
        "crm": ["view"],
    },
    "انبار": {
        "catalog": ["view", "change"],          # stock updates
        "guides": ["view", "add", "change"],    # buying guide questions
        "orders": ["view", "change"],           # mark shipped
    },
}


def setup_groups():
    from django.contrib.auth.models import Group, Permission

    created = []
    for group_name, app_map in PERMISSIONS.items():
        group, g_created = Group.objects.get_or_create(name=group_name)
        if g_created:
            created.append(group_name)
        perms = []
        for app_label, actions in app_map.items():
            codenames = [f"{action}_{app_label_model}" for app_label_model in _model_names(app_label) for action in actions]
            perms.extend(Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames))
        group.permissions.set(perms)
    return created


def _model_names(app_label):
    from django.apps import apps as django_apps

    return [m.__name__.lower() for m in django_apps.get_app_config(app_label).get_models()]
