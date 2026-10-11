SHOPKEEPER_GROUP = "Shopkeeper"


def is_shopkeeper(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and (user.is_superuser or user.groups.filter(name=SHOPKEEPER_GROUP).exists())
    )