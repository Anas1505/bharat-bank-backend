from datetime import datetime
from bson import ObjectId
from . import BaseModel


class Notification(BaseModel):
    """Notification model class"""

    collection_name = "notifications"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'read' not in self.data:
            self.data['read'] = False
        if 'type' not in self.data:
            self.data['type'] = 'system'

    def json(self):
        """Convert notification to JSON-safe dict"""
        return self.to_dict()

    @staticmethod
    def get_user_notifications(user_id, limit=50, skip=0):
        """Get notifications for a user, newest first"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return Notification.find(
            {'user_id': user_id},
            limit=limit,
            skip=skip,
            sort=[('created_at', -1)],
        )

    @staticmethod
    def get_unread_count(user_id):
        """Count unread notifications for a user"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return Notification.count_documents({
            'user_id': user_id,
            'read': False,
        })

    def mark_as_read(self):
        """Mark this notification as read"""
        self.read = True
        self.save()


def create_notification(user_id, message, notification_type='system'):
    """Reusable helper to insert a notification document.

    Args:
        user_id: str or ObjectId of the user
        message: notification message text
        notification_type: one of 'transaction', 'security', 'system'
    """
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)

    notification = Notification(
        user_id=user_id,
        message=message,
        type=notification_type,
    )
    try:
        notification.save()
    except Exception:
        # Notification creation should never break the main flow
        pass
    return notification
