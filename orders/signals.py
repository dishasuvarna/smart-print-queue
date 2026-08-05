from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Handout


@receiver(post_save, sender=Handout)
def notify_shopkeeper_of_new_handout(sender, instance, created, **kwargs):
    if created and not instance.is_active:
        from notifications.tasks import send_new_handout_alert
        send_new_handout_alert.delay(instance.id)