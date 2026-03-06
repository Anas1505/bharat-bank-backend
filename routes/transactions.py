from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import Schema, fields, ValidationError, validate
from bson import ObjectId
from datetime import datetime, timedelta
from extensions import limiter
from models.transaction import Transaction
from models.account import Account
from models.user import User
from utils.validation import validate_transaction_amount, sanitize_input
from utils.security import SecurityAudit, log_security_event, check_suspicious_activity
from utils.notifications import NotificationService

# Create blueprint
transactions_bp = Blueprint('transactions', __name__)

# Schemas for request validation
class CreateTransactionSchema(Schema):
    from_account_id = fields.Str(required=True)
    to_account_id = fields.Str(allow_none=True)
    type = fields.Str(required=True, validate=validate.OneOf([
        'deposit', 'withdrawal', 'transfer', 'payment'
    ]))
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    description = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    category = fields.Str(missing='other', validate=validate.OneOf([
        'food_dining', 'shopping', 'transportation', 'entertainment',
        'healthcare', 'utilities', 'groceries', 'education', 'travel',
        'fitness', 'insurance', 'investment', 'salary', 'business', 'other'
    ]))
    recipient_info = fields.Dict(missing={})

class TransferSchema(Schema):
    from_account_id = fields.Str(required=True)
    to_account_id = fields.Str(required=True)
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    description = fields.Str(missing='Transfer')
    category = fields.Str(missing='transfer')

class ExternalPaymentSchema(Schema):
    from_account_id = fields.Str(required=True)
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    recipient = fields.Dict(required=True)
    description = fields.Str(required=True)
    category = fields.Str(missing='payment')
    payment_method = fields.Str(missing='ach', validate=validate.OneOf(['ach', 'wire', 'check']))

class TransactionHistorySchema(Schema):
    account_id = fields.Str(allow_none=True)
    start_date = fields.DateTime(allow_none=True)
    end_date = fields.DateTime(allow_none=True)
    transaction_type = fields.Str(allow_none=True, validate=validate.OneOf([
        'deposit', 'withdrawal', 'transfer', 'payment', 'fee', 'interest', 'refund'
    ]))
    category = fields.Str(allow_none=True)
    min_amount = fields.Float(allow_none=True, validate=validate.Range(min=0))
    max_amount = fields.Float(allow_none=True, validate=validate.Range(min=0))
    status = fields.Str(allow_none=True, validate=validate.OneOf([
        'pending', 'completed', 'failed', 'cancelled', 'reversed'
    ]))
    limit = fields.Int(missing=50, validate=validate.Range(min=1, max=100))
    offset = fields.Int(missing=0, validate=validate.Range(min=0))

@transactions_bp.route('/', methods=['GET'])
@jwt_required()
def get_transactions():
    """Get transaction history for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate query parameters
        schema = TransactionHistorySchema()
        try:
            filters = schema.load(request.args.to_dict())
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': 'Invalid query parameters',
                'errors': e.messages
            }), 400
        
        # Build query
        query = {'user_id': ObjectId(current_user_id)}
        
        # Add filters
        if filters.get('account_id'):
            try:
                account_id = ObjectId(filters['account_id'])
                # Verify user owns the account
                account = Account.find_by_id(filters['account_id'])
                if not account or str(account.user_id) != current_user_id:
                    return jsonify({
                        'success': False,
                        'message': 'Invalid account or access denied'
                    }), 403
                    
                query['$or'] = [
                    {'from_account_id': account_id},
                    {'to_account_id': account_id}
                ]
            except:
                return jsonify({
                    'success': False,
                    'message': 'Invalid account ID'
                }), 400
        
        if filters.get('transaction_type'):
            query['type'] = filters['transaction_type']
        
        if filters.get('category'):
            query['category'] = filters['category']
        
        if filters.get('status'):
            query['status'] = filters['status']
        
        # Date range filter
        if filters.get('start_date') or filters.get('end_date'):
            date_filter = {}
            if filters.get('start_date'):
                date_filter['$gte'] = filters['start_date']
            if filters.get('end_date'):
                date_filter['$lte'] = filters['end_date']
            query['created_at'] = date_filter
        
        # Amount range filter
        if filters.get('min_amount') or filters.get('max_amount'):
            amount_filter = {}
            if filters.get('min_amount'):
                amount_filter['$gte'] = filters['min_amount']
            if filters.get('max_amount'):
                amount_filter['$lte'] = filters['max_amount']
            query['amount'] = amount_filter
        
        # Get transactions
        transactions = Transaction.find(
            query,
            limit=filters['limit'],
            skip=filters['offset'],
            sort=[('created_at', -1)]
        )
        
        # Get total count for pagination
        total_count = Transaction.count_documents(query)
        
        return jsonify({
            'success': True,
            'data': {
                'transactions': [tx.json() for tx in transactions],
                'pagination': {
                    'total': total_count,
                    'limit': filters['limit'],
                    'offset': filters['offset'],
                    'has_more': total_count > (filters['offset'] + filters['limit'])
                }
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve transactions'
        }), 500

@transactions_bp.route('/<transaction_id>', methods=['GET'])
@jwt_required()
def get_transaction(transaction_id):
    """Get specific transaction details"""
    try:
        current_user_id = get_jwt_identity()
        
        # Validate transaction ID
        try:
            ObjectId(transaction_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid transaction ID'
            }), 400
        
        # Find transaction
        transaction = Transaction.find_by_id(transaction_id)
        if not transaction:
            return jsonify({
                'success': False,
                'message': 'Transaction not found'
            }), 404
        
        # Check ownership
        if str(transaction.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        return jsonify({
            'success': True,
            'data': {
                'transaction': transaction.json()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve transaction'
        }), 500

@transactions_bp.route('/deposit', methods=['POST'])
@jwt_required()
@limiter.limit("20 per hour")
def create_deposit():
    """Create a deposit transaction"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        data = request.get_json() or {}
        
        # Required fields for deposit
        if not all(key in data for key in ['to_account_id', 'amount', 'description']):
            return jsonify({
                'success': False,
                'message': 'Missing required fields: to_account_id, amount, description'
            }), 400
        
        # Validate amount
        try:
            validate_transaction_amount(data['amount'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Validate account
        try:
            ObjectId(data['to_account_id'])
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        account = Account.find_by_id(data['to_account_id'])
        if not account or str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Invalid account or access denied'
            }), 403
        
        # Create transaction
        transaction_data = {
            'user_id': ObjectId(current_user_id),
            'to_account_id': ObjectId(data['to_account_id']),
            'type': 'deposit',
            'amount': data['amount'],
            'description': sanitize_input(data['description']),
            'category': data.get('category', 'other'),
            'currency': account.currency,
            'method': 'mobile_app'
        }
        
        transaction = Transaction(**transaction_data)
        
        # Process the transaction
        if transaction.process_transaction():
            # Log security event
            SecurityAudit.audit_transaction(
                transaction.transaction_id,
                current_user_id,
                data['amount'],
                'deposit'
            )
            
            # Send notification
            NotificationService.send_transaction_notification(
                user.email,
                transaction.get_transaction_summary()
            )
            
            return jsonify({
                'success': True,
                'message': 'Deposit completed successfully',
                'data': {
                    'transaction': transaction.json()
                }
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Deposit failed',
                'details': getattr(transaction, 'failure_reason', 'Unknown error')
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to process deposit'
        }), 500

@transactions_bp.route('/withdrawal', methods=['POST'])
@jwt_required()
@limiter.limit("15 per hour")
def create_withdrawal():
    """Create a withdrawal transaction"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        data = request.get_json() or {}
        
        # Required fields for withdrawal
        if not all(key in data for key in ['from_account_id', 'amount', 'description']):
            return jsonify({
                'success': False,
                'message': 'Missing required fields: from_account_id, amount, description'
            }), 400
        
        # Validate amount
        try:
            validate_transaction_amount(data['amount'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Validate account
        try:
            ObjectId(data['from_account_id'])
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        account = Account.find_by_id(data['from_account_id'])
        if not account or str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Invalid account or access denied'
            }), 403
        
        # Check for suspicious activity
        suspicious_check = check_suspicious_activity(
            current_user_id,
            'transaction',
            amount=data['amount'],
            last_activity_time=user.last_login
        )
        
        # Create transaction
        transaction_data = {
            'user_id': ObjectId(current_user_id),
            'from_account_id': ObjectId(data['from_account_id']),
            'type': 'withdrawal',
            'amount': data['amount'],
            'description': sanitize_input(data['description']),
            'category': data.get('category', 'other'),
            'currency': account.currency,
            'method': 'mobile_app'
        }
        
        transaction = Transaction(**transaction_data)
        
        # Process the transaction
        if transaction.process_transaction():
            # Log security event
            SecurityAudit.audit_transaction(
                transaction.transaction_id,
                current_user_id,
                data['amount'],
                'withdrawal'
            )
            
            # Send notification
            NotificationService.send_transaction_notification(
                user.email,
                transaction.get_transaction_summary()
            )
            
            # Send security alert if suspicious
            if suspicious_check.get('is_suspicious'):
                NotificationService.send_security_alert(
                    user.email,
                    user.first_name,
                    'Large Withdrawal Alert',
                    {
                        'amount': f"{account.currency} {data['amount']:.2f}",
                        'account': account.get_masked_account_number(),
                        'indicators': suspicious_check['indicators']
                    }
                )
            
            return jsonify({
                'success': True,
                'message': 'Withdrawal completed successfully',
                'data': {
                    'transaction': transaction.json()
                }
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Withdrawal failed',
                'details': getattr(transaction, 'failure_reason', 'Unknown error')
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to process withdrawal'
        }), 500

@transactions_bp.route('/transfer', methods=['POST'])
@jwt_required()
@limiter.limit("15 per hour")
def create_transfer():
    """Create a transfer transaction"""
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
        
        # Check ownership of from account (user can transfer to any account)
        if str(from_account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied to source account'
            }), 403
        
        # Create transaction
        transaction_data = {
            'user_id': ObjectId(current_user_id),
            'from_account_id': from_id,
            'to_account_id': to_id,
            'type': 'transfer',
            'amount': data['amount'],
            'description': sanitize_input(data['description']),
            'category': data.get('category', 'transfer'),
            'currency': from_account.currency,
            'method': 'mobile_app'
        }
        
        transaction = Transaction(**transaction_data)
        
        # Process the transaction
        if transaction.process_transaction():
            # Log security event
            SecurityAudit.audit_transaction(
                transaction.transaction_id,
                current_user_id,
                data['amount'],
                'transfer'
            )
            
            # Send notification to sender
            NotificationService.send_transaction_notification(
                user.email,
                transaction.get_transaction_summary()
            )
            
            # If transferring to different user, notify recipient
            if str(to_account.user_id) != current_user_id:
                recipient = User.find_by_id(to_account.user_id)
                if recipient:
                    NotificationService.send_transaction_notification(
                        recipient.email,
                        {
                            **transaction.get_transaction_summary(),
                            'description': f"Transfer received from {user.first_name} {user.last_name}"
                        }
                    )
            
            return jsonify({
                'success': True,
                'message': 'Transfer completed successfully',
                'data': {
                    'transaction': transaction.json()
                }
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Transfer failed',
                'details': getattr(transaction, 'failure_reason', 'Unknown error')
            }), 400
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to process transfer'
        }), 500

@transactions_bp.route('/payment', methods=['POST'])
@jwt_required(fresh=True)
@limiter.limit("10 per hour")
def create_payment():
    """Create an external payment transaction"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = ExternalPaymentSchema()
        data = schema.load(request.get_json() or {})
        
        # Validate amount
        try:
            validate_transaction_amount(data['amount'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Validate account
        try:
            ObjectId(data['from_account_id'])
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid account ID'
            }), 400
        
        account = Account.find_by_id(data['from_account_id'])
        if not account or str(account.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Invalid account or access denied'
            }), 403
        
        # Validate recipient information
        recipient = data.get('recipient', {})
        required_recipient_fields = ['name', 'account_number']
        if not all(field in recipient for field in required_recipient_fields):
            return jsonify({
                'success': False,
                'message': 'Missing required recipient information'
            }), 400
        
        # Create transaction
        transaction_data = {
            'user_id': ObjectId(current_user_id),
            'from_account_id': ObjectId(data['from_account_id']),
            'type': 'payment',
            'amount': data['amount'],
            'description': sanitize_input(data['description']),
            'category': data.get('category', 'payment'),
            'currency': account.currency,
            'method': data.get('payment_method', 'ach'),
            'recipient_info': recipient
        }
        
        transaction = Transaction(**transaction_data)
        
        # Process the transaction
        if transaction.process_transaction():
            # Log security event
            SecurityAudit.audit_transaction(
                transaction.transaction_id,
                current_user_id,
                data['amount'],
                'payment'
            )
            
            # Send notification
            NotificationService.send_transaction_notification(
                user.email,
                transaction.get_transaction_summary()
            )
            
            return jsonify({
                'success': True,
                'message': 'Payment processed successfully',
                'data': {
                    'transaction': transaction.json()
                }
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Payment failed',
                'details': getattr(transaction, 'failure_reason', 'Unknown error')
            }), 400
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to process payment'
        }), 500

@transactions_bp.route('/<transaction_id>/reverse', methods=['POST'])
@jwt_required(fresh=True)
@limiter.limit("5 per hour")
def reverse_transaction(transaction_id):
    """Reverse a completed transaction"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate transaction ID
        try:
            ObjectId(transaction_id)
        except:
            return jsonify({
                'success': False,
                'message': 'Invalid transaction ID'
            }), 400
        
        # Find transaction
        transaction = Transaction.find_by_id(transaction_id)
        if not transaction:
            return jsonify({
                'success': False,
                'message': 'Transaction not found'
            }), 404
        
        # Check ownership
        if str(transaction.user_id) != current_user_id:
            return jsonify({
                'success': False,
                'message': 'Access denied'
            }), 403
        
        # Check if transaction can be reversed
        if transaction.status != 'completed':
            return jsonify({
                'success': False,
                'message': 'Only completed transactions can be reversed'
            }), 400
        
        # Check if transaction is too old to reverse (e.g., 30 days)
        if hasattr(transaction, 'created_at'):
            age_limit = datetime.utcnow() - timedelta(days=30)
            if transaction.created_at < age_limit:
                return jsonify({
                    'success': False,
                    'message': 'Transaction is too old to reverse'
                }), 400
        
        # Get reversal reason
        data = request.get_json() or {}
        reason = sanitize_input(data.get('reason', 'User requested reversal'))
        
        # Reverse the transaction
        reversal = transaction.reverse_transaction(reason)
        
        if reversal:
            # Log security event
            log_security_event('transaction_reversed', current_user_id, {
                'original_transaction_id': transaction_id,
                'reversal_transaction_id': str(reversal._id),
                'reason': reason
            })
            
            # Send notification
            NotificationService.send_transaction_notification(
                user.email,
                reversal.get_transaction_summary()
            )
            
            return jsonify({
                'success': True,
                'message': 'Transaction reversed successfully',
                'data': {
                    'original_transaction': transaction.json(),
                    'reversal_transaction': reversal.json()
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to reverse transaction'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to reverse transaction'
        }), 500

@transactions_bp.route('/pending', methods=['GET'])
@jwt_required()
def get_pending_transactions():
    """Get pending transactions for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        
        # Get pending transactions
        pending_transactions = Transaction.get_pending_transactions(current_user_id)
        
        return jsonify({
            'success': True,
            'data': {
                'pending_transactions': [tx.json() for tx in pending_transactions],
                'count': len(pending_transactions)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve pending transactions'
        }), 500

@transactions_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_transaction_summary():
    """Get transaction summary for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        
        # Get date range (default last 30 days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # Allow custom date range
        if request.args.get('start_date'):
            try:
                start_date = datetime.fromisoformat(request.args.get('start_date'))
            except:
                pass
        
        if request.args.get('end_date'):
            try:
                end_date = datetime.fromisoformat(request.args.get('end_date'))
            except:
                pass
        
        # Build query
        query = {
            'user_id': ObjectId(current_user_id),
            'created_at': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        # Get all transactions in range
        transactions = Transaction.find(query)
        
        # Calculate summary statistics
        total_transactions = len(transactions)
        total_deposits = sum(tx.amount for tx in transactions if tx.type == 'deposit')
        total_withdrawals = sum(tx.amount for tx in transactions if tx.type in ['withdrawal', 'payment'])
        total_transfers_out = sum(tx.amount for tx in transactions if tx.type == 'transfer')
        
        # Get transactions by category
        categories = {}
        for tx in transactions:
            category = tx.category
            if category not in categories:
                categories[category] = {'count': 0, 'total_amount': 0}
            categories[category]['count'] += 1
            categories[category]['total_amount'] += tx.amount
        
        # Get transactions by status
        status_counts = {}
        for tx in transactions:
            status = tx.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        summary = {
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'totals': {
                'transactions': total_transactions,
                'deposits': round(total_deposits, 2),
                'withdrawals': round(total_withdrawals, 2),
                'transfers_out': round(total_transfers_out, 2),
                'net_flow': round(total_deposits - total_withdrawals - total_transfers_out, 2)
            },
            'by_category': categories,
            'by_status': status_counts
        }
        
        return jsonify({
            'success': True,
            'data': summary
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to generate transaction summary'
        }), 500
