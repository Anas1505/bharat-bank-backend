from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from models.notification import Notification, DEFAULT_NOTIFICATION_SETTINGS
from models.user import User

# Create blueprint
notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/', methods=['GET'])
@jwt_required()
def get_notifications():
    """Get all notifications for the authenticated user"""
    try:
        current_user_id = get_jwt_identity()

        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))

        notifications = Notification.get_user_notifications(
            current_user_id, limit=limit, skip=offset,
        )
        total = Notification.count_documents({
            'user_id': ObjectId(current_user_id),
        })
        unread = Notification.get_unread_count(current_user_id)

        return jsonify({
            'success': True,
            'data': {
                'notifications': [n.json() for n in notifications],
                'unread_count': unread,
                'pagination': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'has_more': total > (offset + limit),
                },
            },
        })

    except Exception:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve notifications',
        }), 500


@notifications_bp.route('/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """Get count of unread notifications"""
    try:
        current_user_id = get_jwt_identity()
        count = Notification.get_unread_count(current_user_id)
        return jsonify({
            'success': True,
            'data': {'unread_count': count},
        })
    except Exception:
        return jsonify({
            'success': False,
            'message': 'Failed to get unread count',
        }), 500


@notifications_bp.route('/read/<notification_id>', methods=['PATCH'])
@jwt_required()
def mark_as_read(notification_id):
    """Mark a notification as read"""
    try:
        current_user_id = get_jwt_identity()

        try:
            ObjectId(notification_id)
        except Exception:
            return jsonify({
                'success': False,
                'message': 'Invalid notification ID',
            }), 400

        notification = Notification.find_by_id(notification_id)
        if not notification:
            return jsonify({
                'success': False,
                'message': 'Notification not found',
            }), 404

        # Ensure the notification belongs to the current user
        if str(notification.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied',
            }), 403

        notification.mark_as_read()

        return jsonify({
            'success': True,
            'message': 'Notification marked as read',
        })

    except Exception:
        return jsonify({
            'success': False,
            'message': 'Failed to update notification',
        }), 500


@notifications_bp.route('/settings', methods=['GET'])
@jwt_required()
def get_notification_settings():
    """Get notification preferences for the authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)

        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found',
            }), 404

        # Merge defaults with whatever the user has stored
        saved = getattr(user, 'notification_settings', None) or {}
        settings = {**DEFAULT_NOTIFICATION_SETTINGS, **saved}

        return jsonify({
            'success': True,
            'data': {'notification_settings': settings},
        })

    except Exception:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve notification settings',
        }), 500


@notifications_bp.route('/settings', methods=['PUT'])
@jwt_required()
def update_notification_settings():
    """Update notification preferences for the authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)

        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found',
            }), 404

        data = request.get_json() or {}
        incoming = data.get('notification_settings', {})

        if not incoming:
            return jsonify({
                'success': False,
                'message': 'No settings provided',
            }), 400

        # Only accept known keys
        valid_keys = set(DEFAULT_NOTIFICATION_SETTINGS.keys())
        current = getattr(user, 'notification_settings', None) or {**DEFAULT_NOTIFICATION_SETTINGS}

        updated_keys = []
        for key, value in incoming.items():
            if key in valid_keys and isinstance(value, bool):
                current[key] = value
                updated_keys.append(key)

        user.notification_settings = current
        user.save()

        return jsonify({
            'success': True,
            'message': 'Notification settings updated',
            'data': {
                'notification_settings': current,
                'updated_keys': updated_keys,
            },
        })

    except Exception:
        return jsonify({
            'success': False,
            'message': 'Failed to update notification settings',
        }), 500


@notifications_bp.route('/<notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        current_user_id = get_jwt_identity()

        try:
            ObjectId(notification_id)
        except Exception:
            return jsonify({
                'success': False,
                'message': 'Invalid notification ID',
            }), 400

        notification = Notification.find_by_id(notification_id)
        if not notification:
            return jsonify({
                'success': False,
                'message': 'Notification not found',
            }), 404

        if str(notification.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied',
            }), 403

        notification.delete()

        return jsonify({
            'success': True,
            'message': 'Notification deleted',
        })

    except Exception:
        return jsonify({
            'success': False,
            'message': 'Failed to delete notification',
        }), 500
