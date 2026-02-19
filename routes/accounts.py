from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import Schema, fields, ValidationError, validate
from bson import ObjectId
from datetime import datetime
from extensions import limiter
from models.account import Account
from models.user import User
from utils.validation import validate_transaction_amount, sanitize_input
from utils.security import SecurityAudit, log_security_event, check_suspicious_activity
from utils.notifications import NotificationService

# Create blueprint
accounts_bp = Blueprint('accounts', __name__)

# Schemas for request validation
class CreateAccountSchema(Schema):
    account_type = fields.Str(required=True, validate=validate.OneOf(['checking', 'savings', 'credit']))
    initial_deposit = fields.Float(missing=0.0)
    currency = fields.Str(missing='USD', validate=validate.OneOf(['USD', 'EUR', 'GBP']))
    nickname = fields.Str(missing=None, validate=validate.Length(max=50))

class UpdateAccountSchema(Schema):
    nickname = fields.Str(validate=validate.Length(max=50))
    daily_transaction_limit = fields.Float(validate=validate.Range(min=100, max=50000))
    monthly_transaction_limit = fields.Float(validate=validate.Range(min=1000, max=200000))
    notifications_enabled = fields.Bool()

class FreezeAccountSchema(Schema):
    reason = fields.Str(required=True, validate=validate.OneOf([
        'user_request', 'suspicious_activity', 'lost_card', 'security_concern', 'other'
    ]))
    notes = fields.Str(missing='')

class TransferSchema(Schema):
    from_account_id = fields.Str(required=True)
    to_account_id = fields.Str(required=True)
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    description = fields.Str(missing='Internal transfer')

@accounts_bp.route('/', methods=['GET'])
@jwt_required()
def get_accounts():
    """Get all accounts for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Get query parameters
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        include_balance = request.args.get('include_balance', 'true').lower() == 'true'
        
        # Get user accounts
        accounts = Account.get_user_accounts(user._id, active_only=active_only)
        
        account_data = []
        for account in accounts:
            data = account.json()
            if not include_balance:
                data.pop('balance', None)
                data.pop('available_balance', None)
            account_data.append(data)
        
        return jsonify({
            'success': True,
            'data': {
                'accounts': account_data,
                'total_accounts': len(account_data)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve accounts'
        }), 500

@accounts_bp.route('/<account_id>', methods=['GET'])
@jwt_required()
def get_account(account_id):
    """Get specific account details"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        return jsonify({
            'success': True,
            'data': {
                'account': account.json()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve account'
        }), 500

@accounts_bp.route('/', methods=['POST'])
@jwt_required(fresh=True)
@limiter.limit("3 per hour")
def create_account():
    """Create new account for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = CreateAccountSchema()
        data = schema.load(request.get_json() or {})
        
        # Check if user already has maximum number of accounts (e.g., 5)
        existing_accounts = Account.get_user_accounts(user._id)
        if len(existing_accounts) >= 5:
            return jsonify({
                'success': False,
                'message': 'Maximum number of accounts reached'
            }), 400
        
        # Validate initial deposit
        if data.get('initial_deposit', 0) > 0:
            try:
                validate_transaction_amount(data['initial_deposit'])
            except ValidationError as e:
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 400
        
        # Sanitize nickname
        if data.get('nickname'):
            data['nickname'] = sanitize_input(data['nickname'])
        
        # Create account
        account_data = {
            'user_id': user._id,
            'account_type': data['account_type'],
            'balance': data.get('initial_deposit', 0.0),
            'currency': data.get('currency', 'USD'),
            'nickname': data.get('nickname'),
            'is_primary': len(existing_accounts) == 0  # First account is primary
        }
        
        account = Account(**account_data)
        
        if account.save():
            # Log security event
            SecurityAudit.audit_account_change(
                current_user_id, 
                'account_created', 
                str(account._id)
            )
            
            # Send notification
            NotificationService.send_account_status_change(
                user.email,
                user.first_name,
                account.account_number,
                'created',
                f"New {data['account_type']} account created"
            )
            
            return jsonify({
                'success': True,
                'message': 'Account created successfully',
                'data': {
                    'account': account.json()
                }
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to create account'
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
            'message': 'Failed to create account'
        }), 500

@accounts_bp.route('/<account_id>', methods=['PUT'])
@jwt_required()
def update_account(account_id):
    """Update account settings"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Validate request data
        schema = UpdateAccountSchema()
        data = schema.load(request.get_json() or {})
        
        # Update account fields
        updated_fields = []
        if 'nickname' in data:
            account.nickname = sanitize_input(data['nickname']) if data['nickname'] else None
            updated_fields.append('nickname')
        
        if 'daily_transaction_limit' in data:
            account.daily_transaction_limit = data['daily_transaction_limit']
            updated_fields.append('daily_transaction_limit')
        
        if 'monthly_transaction_limit' in data:
            account.monthly_transaction_limit = data['monthly_transaction_limit']
            updated_fields.append('monthly_transaction_limit')
        
        if 'notifications_enabled' in data:
            account.notifications_enabled = data['notifications_enabled']
            updated_fields.append('notifications_enabled')
        
        if not updated_fields:
            return jsonify({
                'success': False,
                'message': 'No valid fields to update'
            }), 400
        
        if account.save():
            # Log security event
            SecurityAudit.audit_account_change(
                current_user_id,
                'account_updated',
                account_id
            )
            
            return jsonify({
                'success': True,
                'message': 'Account updated successfully',
                'data': {
                    'account': account.json(),
                    'updated_fields': updated_fields
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update account'
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
            'message': 'Failed to update account'
        }), 500

@accounts_bp.route('/<account_id>/set-primary', methods=['POST'])
@jwt_required()
def set_primary_account(account_id):
    """Set account as primary"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if account is active
        if not account.is_active:
            return jsonify({
                'success': False,
                'message': 'Cannot set inactive account as primary'
            }), 400
        
        # Set as primary
        account.set_as_primary()
        
        # Log security event
        SecurityAudit.audit_account_change(
            current_user_id,
            'primary_account_changed',
            account_id
        )
        
        return jsonify({
            'success': True,
            'message': 'Primary account updated successfully',
            'data': {
                'account': account.json()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to update primary account'
        }), 500

@accounts_bp.route('/<account_id>/freeze', methods=['POST'])
@jwt_required(fresh=True)
def freeze_account(account_id):
    """Freeze account"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if account is already frozen
        if account.is_frozen:
            return jsonify({
                'success': False,
                'message': 'Account is already frozen'
            }), 400
        
        # Validate request data
        schema = FreezeAccountSchema()
        data = schema.load(request.get_json() or {})
        
        # Freeze account
        reason = data.get('reason', 'user_request')
        notes = sanitize_input(data.get('notes', ''))
        
        account.freeze_account(reason)
        if notes:
            account.freeze_notes = notes
            account.save()
        
        # Log security event
        SecurityAudit.audit_account_change(
            current_user_id,
            'account_frozen',
            account_id
        )
        
        # Send notification
        NotificationService.send_account_status_change(
            user.email,
            user.first_name,
            account.account_number,
            'frozen',
            reason
        )
        
        return jsonify({
            'success': True,
            'message': 'Account frozen successfully',
            'data': {
                'account': account.json()
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
            'message': 'Failed to freeze account'
        }), 500

@accounts_bp.route('/<account_id>/unfreeze', methods=['POST'])
@jwt_required(fresh=True)
def unfreeze_account(account_id):
    """Unfreeze account"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if account is frozen
        if not account.is_frozen:
            return jsonify({
                'success': False,
                'message': 'Account is not frozen'
            }), 400
        
        # Unfreeze account
        account.unfreeze_account()
        
        # Log security event
        SecurityAudit.audit_account_change(
            current_user_id,
            'account_unfrozen',
            account_id
        )
        
        # Send notification
        NotificationService.send_account_status_change(
            user.email,
            user.first_name,
            account.account_number,
            'active',
            'Account has been unfrozen'
        )
        
        return jsonify({
            'success': True,
            'message': 'Account unfrozen successfully',
            'data': {
                'account': account.json()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to unfreeze account'
        }), 500

@accounts_bp.route('/<account_id>/balance', methods=['GET'])
@jwt_required()
def get_account_balance(account_id):
    """Get current account balance"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        return jsonify({
            'success': True,
            'data': {
                'account_id': account_id,
                'account_number': account.get_masked_account_number(),
                'balance': account.balance,
                'available_balance': account.available_balance,
                'currency': account.currency,
                'last_updated': account.updated_at.isoformat() if hasattr(account, 'updated_at') else None
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve balance'
        }), 500

@accounts_bp.route('/transfer', methods=['POST'])
@jwt_required(fresh=True)
@limiter.limit("10 per hour")
def internal_transfer():
    """Transfer money between user's accounts"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = TransferSchema()
        data = schema.load(request.get_json() or {})
        
        # Validate amount
        try:
            validate_transaction_amount(data['amount'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Validate account IDs
        try:
            from_id = ObjectId(data['from_account_id'])
            to_id = ObjectId(data['to_account_id'])
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account IDs'
            }), 400
        
        if data['from_account_id'] == data['to_account_id']:
            return jsonify({
                'success': False,
                'message': 'Cannot transfer to the same account'
            }), 400
        
        # Find accounts
        from_account = Account.find_by_id(data['from_account_id'])
        to_account = Account.find_by_id(data['to_account_id'])
        
        if not from_account or not to_account:
            return jsonify({
                'success': False,
                'message': 'One or both accounts not found'
            }), 404
        
        # Check ownership of both accounts
        if str(from_account.user_id) != current_user_id or str(to_account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'You can only transfer between your own accounts'
            }), 403
        
        # Check if from account can transact
        can_transact = from_account.can_transact(data['amount'], 'debit')
        if not can_transact['allowed']:
            return jsonify({
                'success': False,
                'message': can_transact['reason']
            }), 400
        
        # Check for suspicious activity
        suspicious_check = check_suspicious_activity(
            current_user_id,
            'transaction',
            amount=data['amount']
        )
        
        # Perform transfer
        from_account.update_balance(data['amount'], 'debit')
        to_account.update_balance(data['amount'], 'credit')
        
        # Log security event
        log_security_event('internal_transfer', current_user_id, {
            'from_account': data['from_account_id'],
            'to_account': data['to_account_id'],
            'amount': data['amount'],
            'description': data.get('description', ''),
            'suspicious_score': suspicious_check.get('risk_score', 0)
        })
        
        # Send notification if suspicious
        if suspicious_check.get('is_suspicious'):
            NotificationService.send_security_alert(
                user.email,
                user.first_name,
                'Large Transfer Alert',
                {
                    'amount': f"{from_account.currency} {data['amount']:.2f}",
                    'from_account': from_account.get_masked_account_number(),
                    'to_account': to_account.get_masked_account_number()
                }
            )
        
        return jsonify({
            'success': True,
            'message': 'Transfer completed successfully',
            'data': {
                'transfer': {
                    'from_account': {
                        'id': data['from_account_id'],
                        'balance': from_account.balance
                    },
                    'to_account': {
                        'id': data['to_account_id'],
                        'balance': to_account.balance
                    },
                    'amount': data['amount'],
                    'description': data.get('description', ''),
                    'timestamp': datetime.utcnow().isoformat()
                }
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
            'message': 'Transfer failed'
        }), 500

@accounts_bp.route('/<account_id>/summary', methods=['GET'])
@jwt_required()
def get_account_summary(account_id):
    """Get account summary with recent activity"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate account ID
        try:
            ObjectId(account_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        # Find account
        account = Account.find_by_id(account_id)
        if not account:
            return jsonify({
                'success': False,
                'message': 'Account not found'
            }), 404
        
        # Check ownership
        if str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Get recent transactions (would need Transaction model import)
        from models.transaction import Transaction
        recent_transactions = Transaction.get_account_transactions(account_id, limit=5)
        
        summary = {
            'account': account.json(),
            'recent_transactions': [tx.json() for tx in recent_transactions],
            'statistics': {
                'total_transactions': len(recent_transactions),
                'account_age_days': (datetime.utcnow() - account.created_at).days if hasattr(account, 'created_at') else 0
            }
        }
        
        return jsonify({
            'success': True,
            'data': summary
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve account summary'
        }), 500
