from .models import Notification


def unread_notifications(request):
    """Передать в шаблоны число непрочитанных уведомлений для шапки"""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    count = Notification.objects.filter(owner=user, read_at__isnull=True).count()
    return {"unread_notifications": count}
