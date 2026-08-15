from .utils import encrypt_id

def encrypted_user_id(request):
    if request.user.is_authenticated:
        return {'encrypted_user_id': encrypt_id(request.user.id)}
    return {}

def unread_notification_count(request):
    if request.user.is_authenticated:
        from .models import Notification
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'unread_notification_count': count}
    return {'unread_notification_count': 0}
