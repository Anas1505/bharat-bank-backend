from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import Schema, fields, ValidationError, validate
from datetime import datetime, date
from extensions import limiter
from models.user import User
from models.account import Account
from models.transaction import Transaction
from utils.validation import validate_password_strength, sanitize_input
from utils.security import SecurityAudit, log_security_event, check_password_complexity
from utils.notifications import NotificationService

# Create blueprint
users_bp = Blueprint('users', __name__)

# Schemas for request validation
class UpdateProfileSchema(Schema):
    first_name = fields.Str(validate=validate.Length(min=1, max=50))
    last_name = fields.Str(validate=validate.Length(min=1, max=50))
    phone = fields.Str(validate=validate.Length(min=10, max=15))
    date_of_birth = fields.Date()
    address = fields.Dict()
    preferences = fields.Dict()

class UpdatePasswordSchema(Schema):
    current_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=8))
    confirm_password = fields.Str(required=True)

class SecuritySettingsSchema(Schema):
    two_factor_enabled = fields.Bool()
    email_notifications = fields.Bool()
    sms_notifications = fields.Bool()
    login_alerts = fields.Bool()
    transaction_alerts = fields.Bool()

class DeactivateAccountSchema(Schema):
    reason = fields.Str(required=True, validate=validate.OneOf([
        'no_longer_needed', 'security_concern', 'poor_service', 'other'
    ]))
    feedback = fields.Str(validate=validate.Length(max=500))
    confirm_deactivation = fields.Bool(required=True)

@users_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get current user's profile information"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Get user accounts
        accounts = Account.get_user_accounts(user._id)
        
        # Get recent transaction count
        recent_transactions = Transaction.get_user_transactions(
            user._id, limit=10
        )
        
        profile_data = {
            'user': user.json(),
            'accounts_summary': {
                'total_accounts': len(accounts),
                'total_balance': sum(acc.balance for acc in accounts),
                'primary_currency': accounts[0].currency if accounts else 'USD'
            },
            'activity_summary': {
                'recent_transactions': len(recent_transactions),
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
        }
        
        return jsonify({
            'success': True,
            'data': profile_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve profile'
        }), 500

@users_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user's profile information"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = UpdateProfileSchema()
        data = schema.load(request.get_json() or {})
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No valid fields to update'
            }), 400
        
        # Update user fields
        updated_fields = []
        
        if 'first_name' in data:
            user.first_name = sanitize_input(data['first_name'])
            updated_fields.append('first_name')
        
        if 'last_name' in data:
            user.last_name = sanitize_input(data['last_name'])
            updated_fields.append('last_name')
        
        if 'phone' in data:
            user.phone = sanitize_input(data['phone'])
            updated_fields.append('phone')
        
        if 'date_of_birth' in data:
            # Ensure user is at least 18 years old
            if isinstance(data['date_of_birth'], date):
                today = date.today()
                age = today.year - data['date_of_birth'].year - (
                    (today.month, today.day) < (data['date_of_birth'].month, data['date_of_birth'].day)
                )
                if age < 18:
                    return jsonify({
                        'success': False,
                        'message': 'User must be at least 18 years old'
                    }), 400
            
            user.date_of_birth = data['date_of_birth']
            updated_fields.append('date_of_birth')
        
        if 'address' in data:
            if not hasattr(user, 'address'):
                user.address = {}
            user.address.update(data['address'])
            updated_fields.append('address')
        
        if 'preferences' in data:
            if not hasattr(user, 'preferences'):
                user.preferences = {}
            user.preferences.update(data['preferences'])
            updated_fields.append('preferences')
        
        # Save changes
        if user.save():
            # Log security event
            SecurityAudit.audit_account_change(
                current_user_id,
                'profile_updated'
            )
            
            return jsonify({
                'success': True,
                'message': 'Profile updated successfully',
                'data': {
                    'user': user.json(),
                    'updated_fields': updated_fields
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update profile'
            }), 500
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to update profile'
        }), 500

@users_bp.route('/password', methods=['PUT'])
@jwt_required(fresh=True)
def update_password():
    """Update user's password"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = UpdatePasswordSchema()
        data = schema.load(request.get_json() or {})
        
        # Verify current password
        if not user.check_password(data['current_password']):
            return jsonify({
                'success': False,
                'message': 'Current password is incorrect'
            }), 401
        
        # Check if new password matches confirmation
        if data['new_password'] != data['confirm_password']:
            return jsonify({
                'success': False,
                'message': 'New password and confirmation do not match'
            }), 400
        
        # Check if new password is different from current
        if user.check_password(data['new_password']):
            return jsonify({
                'success': False,
                'message': 'New password must be different from current password'
            }), 400
        
        # Validate password strength
        try:
            validate_password_strength(data['new_password'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Get password complexity score
        complexity_score = check_password_complexity(data['new_password'])
        
        # Update password
        user.set_password(data['new_password'])
        user.password_changed_at = datetime.utcnow()
        user.save()
        
        # Send security alert
        NotificationService.send_security_alert(
            user.email,
            user.first_name,
            'Password Changed',
            {
                'action': 'Password was successfully changed',
                'complexity_score': f'{complexity_score}/100'
            }
        )
        
        # Log security event
        log_security_event('password_changed', current_user_id, {
            'complexity_score': complexity_score
        })
        
        return jsonify({
            'success': True,
            'message': 'Password updated successfully',
            'data': {
                'complexity_score': complexity_score
            }
        })
        
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to update password'
        }), 500

@users_bp.route('/security-settings', methods=['GET'])
@jwt_required()
def get_security_settings():
    """Get user's security settings"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Get security settings with defaults
        settings = {
            'two_factor_enabled': getattr(user, 'two_factor_enabled', False),
            'email_notifications': getattr(user, 'email_notifications', True),
            'sms_notifications': getattr(user, 'sms_notifications', False),
            'login_alerts': getattr(user, 'login_alerts', True),
            'transaction_alerts': getattr(user, 'transaction_alerts', True),
            'last_password_change': getattr(user, 'password_changed_at', user.created_at).isoformat() if hasattr(user, 'created_at') else None,
            'account_created': user.created_at.isoformat() if hasattr(user, 'created_at') else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'last_login_ip': getattr(user, 'last_login_ip', None)
        }
        
        return jsonify({
            'success': True,
            'data': {
                'security_settings': settings
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve security settings'
        }), 500

@users_bp.route('/security-settings', methods=['PUT'])
@jwt_required()
def update_security_settings():
    """Update user's security settings"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = SecuritySettingsSchema()
        data = schema.load(request.get_json() or {})
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No valid settings to update'
            }), 400
        
        # Update security settings
        updated_settings = []
        
        if 'two_factor_enabled' in data:
            user.two_factor_enabled = data['two_factor_enabled']
            updated_settings.append('two_factor_enabled')
        
        if 'email_notifications' in data:
            user.email_notifications = data['email_notifications']
            updated_settings.append('email_notifications')
        
        if 'sms_notifications' in data:
            user.sms_notifications = data['sms_notifications']
            updated_settings.append('sms_notifications')
        
        if 'login_alerts' in data:
            user.login_alerts = data['login_alerts']
            updated_settings.append('login_alerts')
        
        if 'transaction_alerts' in data:
            user.transaction_alerts = data['transaction_alerts']
            updated_settings.append('transaction_alerts')
        
        # Save changes
        if user.save():
            # Log security event
            log_security_event('security_settings_changed', current_user_id, {
                'updated_settings': updated_settings
            })
            
            # Send notification if email alerts are enabled
            if getattr(user, 'email_notifications', True):
                NotificationService.send_security_alert(
                    user.email,
                    user.first_name,
                    'Security Settings Changed',
                    {
                        'action': 'Security settings were updated',
                        'changed_settings': updated_settings
                    }
                )
            
            return jsonify({
                'success': True,
                'message': 'Security settings updated successfully',
                'data': {
                    'updated_settings': updated_settings
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update security settings'
            }), 500
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to update security settings'
        }), 500

@users_bp.route('/activity-log', methods=['GET'])
@jwt_required()
def get_activity_log():
    """Get user's recent activity log"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Get query parameters
        limit = min(int(request.args.get('limit', 20)), 100)
        offset = int(request.args.get('offset', 0))
        
        # Get recent transactions
        recent_transactions = Transaction.get_user_transactions(
            user._id, 
            limit=limit//2,  # Half for transactions
            skip=offset//2
        )
        
        # Prepare activity log
        activities = []
        
        # Add transactions to activity log
        for tx in recent_transactions:
            activities.append({
                'type': 'transaction',
                'action': f'{tx.type.title()} transaction',
                'amount': tx.amount,
                'currency': tx.currency,
                'description': tx.description,
                'timestamp': tx.created_at.isoformat() if hasattr(tx, 'created_at') else None,
                'status': tx.status
            })
        
        # Add login activities (would need to store these in database)
        if user.last_login:
            activities.append({
                'type': 'authentication',
                'action': 'Login',
                'timestamp': user.last_login.isoformat(),
                'ip_address': getattr(user, 'last_login_ip', None)
            })
        
        # Sort by timestamp (most recent first)
        activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'data': {
                'activities': activities[:limit],
                'pagination': {
                    'limit': limit,
                    'offset': offset,
                    'has_more': len(activities) > limit
                }
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve activity log'
        }), 500

@users_bp.route('/deactivate', methods=['POST'])
@jwt_required(fresh=True)
@limiter.limit("1 per day")
def deactivate_account():
    """Deactivate user account"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = DeactivateAccountSchema()
        data = schema.load(request.get_json() or {})
        
        # Check confirmation
        if not data.get('confirm_deactivation'):
            return jsonify({
                'success': False,
                'message': 'Account deactivation must be confirmed'
            }), 400
        
        # Check if user has pending transactions
        pending_transactions = Transaction.get_pending_transactions(current_user_id)
        if pending_transactions:
            return jsonify({
                'success': False,
                'message': 'Cannot deactivate account with pending transactions',
                'data': {
                    'pending_transactions': len(pending_transactions)
                }
            }), 400
        
        # Check account balances
        accounts = Account.get_user_accounts(user._id)
        non_zero_accounts = [acc for acc in accounts if acc.balance != 0]
        
        if non_zero_accounts:
            return jsonify({
                'success': False,
                'message': 'Cannot deactivate account with non-zero balances',
                'data': {
                    'accounts_with_balance': [
                        {
                            'account_id': str(acc._id),
                            'balance': acc.balance,
                            'currency': acc.currency
                        } for acc in non_zero_accounts
                    ]
                }
            }), 400
        
        # Deactivate user account
        user.is_active = False
        user.deactivated_at = datetime.utcnow()
        user.deactivation_reason = data.get('reason')
        user.deactivation_feedback = sanitize_input(data.get('feedback', ''))
        
        # Deactivate all accounts
        for account in accounts:
            account.is_active = False
            account.save()
        
        if user.save():
            # Log security event
            log_security_event('account_deactivated', current_user_id, {
                'reason': data.get('reason'),
                'feedback': data.get('feedback', '')
            })
            
            # Send confirmation email
            NotificationService.send_account_status_change(
                user.email,
                user.first_name,
                'ALL ACCOUNTS',
                'deactivated',
                data.get('reason', 'User request')
            )
            
            return jsonify({
                'success': True,
                'message': 'Account deactivated successfully',
                'data': {
                    'deactivated_at': user.deactivated_at.isoformat(),
                    'reactivation_info': 'Contact support to reactivate your account'
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to deactivate account'
            }), 500
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to deactivate account'
        }), 500

@users_bp.route('/export-data', methods=['POST'])
@jwt_required(fresh=True)
@limiter.limit("1 per day")
def export_user_data():
    """Export user data (GDPR compliance)"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Get all user data
        accounts = Account.get_user_accounts(user._id, active_only=False)
        transactions = Transaction.get_user_transactions(user._id, limit=1000)
        
        # Prepare export data
        export_data = {
            'user_profile': user.json(),
            'accounts': [account.json() for account in accounts],
            'transactions': [tx.json() for tx in transactions],
            'export_metadata': {
                'export_date': datetime.utcnow().isoformat(),
                'total_accounts': len(accounts),
                'total_transactions': len(transactions)
            }
        }
        
        # Log the export request
        log_security_event('data_export_requested', current_user_id)
        
        # In a real application, you might:
        # 1. Generate a secure download link
        # 2. Email the user with download instructions
        # 3. Store the export temporarily with expiration
        
        return jsonify({
            'success': True,
            'message': 'Data export prepared successfully',
            'data': export_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to export user data'
        }), 500

@users_bp.route('/delete', methods=['DELETE'])
@jwt_required(fresh=True)
@limiter.limit("1 per week")
def delete_account():
    """Permanently delete user account and all associated data"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Verify account is deactivated first
        if user.is_active:
            return jsonify({
                'success': False,
                'message': 'Account must be deactivated before deletion'
            }), 400
        
        # Check if account was deactivated recently (cooling off period)
        if hasattr(user, 'deactivated_at'):
            deactivation_age = datetime.utcnow() - user.deactivated_at
            if deactivation_age.days < 30:
                return jsonify({
                    'success': False,
                    'message': 'Account must be deactivated for at least 30 days before deletion'
                }), 400
        
        # Get confirmation from request
        data = request.get_json() or {}
        if not data.get('confirm_deletion'):
            return jsonify({
                'success': False,
                'message': 'Account deletion must be confirmed'
            }), 400
        
        # Delete all associated data
        try:
            # Delete transactions
            transactions = Transaction.get_user_transactions(user._id, limit=10000)
            for tx in transactions:
                tx.delete()
            
            # Delete accounts
            accounts = Account.get_user_accounts(user._id, active_only=False)
            for account in accounts:
                account.delete()
            
            # Log final security event before deletion
            log_security_event('account_deleted', current_user_id)
            
            # Delete user
            user.delete()
            
            return jsonify({
                'success': True,
                'message': 'Account and all associated data have been permanently deleted'
            })
            
        except Exception as delete_error:
            return jsonify({
                'success': False,
                'message': 'Failed to delete account data'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to process account deletion'
        }), 500
