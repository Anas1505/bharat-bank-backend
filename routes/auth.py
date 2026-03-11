from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt
)
from marshmallow import Schema, fields, ValidationError, validate
from datetime import datetime, timedelta
from extensions import limiter, revoke_token
from models.user import User, UserSchema
from models.account import Account
from utils.validation import validate_password_strength, validate_pin, sanitize_input
from utils.security import (
    get_client_ip, log_security_event, SecurityAudit,
    check_suspicious_activity, generate_secure_token
)
from utils.notifications import NotificationService

# Create blueprint
auth_bp = Blueprint('auth', __name__)

# Schemas for request validation
class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=1))
    remember_me = fields.Bool(missing=False)

class RegisterSchema(Schema):
    first_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    last_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    email = fields.Email(required=True)
    phone = fields.Str(required=True, validate=validate.Length(min=10, max=10))
    password = fields.Str(required=True, validate=validate.Length(min=8))
    date_of_birth = fields.Date(required=True)
    accept_terms = fields.Bool(required=True)
    transaction_pin = fields.Str(required=True, validate=validate.Length(equal=4))

class PasswordResetRequestSchema(Schema):
    email = fields.Email(required=True)

class PasswordResetSchema(Schema):
    token = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=8))

class ChangePasswordSchema(Schema):
    current_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=8))

# Authentication endpoints
@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Register a new user"""
    try:
        # Fail fast if DB is not configured (prevents NoneType subscripting in mongo.db[...])
        if not current_app.config.get('DB_CONFIGURED'):
            return jsonify({
                'success': False,
                'message': 'Server misconfigured: database not connected. Set MONGODB_URI and redeploy.'
            }), 503

        # Fail fast if DB is configured but unreachable (Atlas IP whitelist / bad URI)
        try:
            from extensions import mongo
            mongo.db.command('ping')
        except Exception:
            return jsonify({
                'success': False,
                'message': 'Database unreachable. Check MongoDB Atlas Network Access (IP whitelist) and MONGODB_URI.',
            }), 503

        # Validate request data
        schema = RegisterSchema()
        data = schema.load(request.get_json() or {})
        
        # Check if terms are accepted
        if not data.get('accept_terms'):
            return jsonify({
                'success': False,
                'message': 'You must accept the terms and conditions'
            }), 400
        
        # Sanitize input data
        for field in ['first_name', 'last_name', 'phone']:
            if field in data:
                data[field] = sanitize_input(data[field])
        
        # Validate password strength
        try:
            validate_password_strength(data['password'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Validate transaction PIN format (4 digits)
        try:
            validate_pin(data.get('transaction_pin'))
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Check if user already exists
        existing_user = User.find_one({'email': data['email'].lower()})
        if existing_user:
            return jsonify({
                'success': False,
                'message': 'User with this email already exists'
            }), 409
        
        # Create new user
        user_data = {
            'first_name': data['first_name'],
            'last_name': data['last_name'],
            'email': data['email'].lower(),
            'phone': data['phone'],
            'password': data['password'],
            'date_of_birth': data['date_of_birth'],
            'is_active': True,
            'is_verified': False,
            'registration_ip': get_client_ip(),
            'last_login': None,
            # transaction PIN fields initialisation
            'pin_attempts': 0,
            'pin_locked_until': None,
            # consent & metadata
            'terms_accepted': True,
        }
        
        user = User(**user_data)
        # Set and hash the transaction PIN before saving
        try:
            user.set_transaction_pin(data['transaction_pin'])
        except ValueError as e:
            return jsonify({
                'success': False,
                'message': str(e),
            }), 400

        if user.save():
            # Create a primary account for the user
            account_data = {
                'user_id': user._id,
                'account_type': 'savings',
                'balance': 0.0,
                'currency': 'INR',
                'is_primary': True
            }
            account = Account(**account_data)
            account.save()
            
            # Log security event
            SecurityAudit.audit_login_attempt(
                str(user._id), True, get_client_ip(),
                request.headers.get('User-Agent', '')
            )
            
            # Send welcome email only if enabled (avoid Render SMTP timeouts)
            try:
                if current_app.config.get('EMAIL_ENABLED', False):
                    NotificationService.send_welcome_email(
                        user.email,
                        user.first_name
                    )
            except Exception:
                pass

            # Create tokens
            access_token = create_access_token(
                identity=str(user._id),
                fresh=True
            )
            refresh_token = create_refresh_token(identity=str(user._id))
            
            primary_account_json = None
            try:
                primary_account_json = account.json()
            except Exception:
                primary_account_json = None

            return jsonify({
                'success': True,
                'message': 'Registration successful',
                'data': {
                    'user': user.json(),
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'primary_account': primary_account_json
                }
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Registration failed. Please try again.'
            }), 500
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc() 
    
        return jsonify({
            'success': False,
            'message': 'Registration failed. Please try again later.'
        }), 500
@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """Authenticate user and return tokens"""
    try:
        # Get and validate request data
        request_data = request.get_json()
        if not request_data:
            return jsonify({
                'success': False,
                'message': 'Request body is required'
            }), 400
        
        # Validate request data
        schema = LoginSchema()
        try:
            data = schema.load(request_data)
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': 'Validation error',
                'errors': e.messages
            }), 400
        
        # Find user
        user = User.find_one({'email': data['email'].lower()})
        if not user:
            # Log failed login attempt
            log_security_event('login_failure', None, {
                'email': data['email'],
                'reason': 'user_not_found'
            })
            return jsonify({
                'success': False,
                'message': 'Invalid email or password'
            }), 401
        
        # Check password
        try:
            password_valid = user.check_password(data['password'])
        except Exception as e:
            current_app.logger.error(f"Password check error: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Invalid email or password'
            }), 401
        
        if not password_valid:
            # Log failed login attempt
            SecurityAudit.audit_login_attempt(
                str(user._id), False, get_client_ip(),
                request.headers.get('User-Agent', '')
            )
            return jsonify({
                'success': False,
                'message': 'Invalid email or password'
            }), 401
        
        # Check if account is active
        if not user.is_active:
            return jsonify({
                'success': False,
                'message': 'Account is deactivated. Please contact support.'
            }), 403
        
        # Check for suspicious activity
        suspicious_check = check_suspicious_activity(
            str(user._id), 
            'login',
            last_activity_time=user.last_login
        )
        
        if suspicious_check['is_suspicious']:
            # Send security alert
            NotificationService.send_security_alert(
                user.email,
                user.first_name,
                'Suspicious Login Activity',
                suspicious_check['indicators']
            )
        
        # Update user login info
        user.last_login = datetime.utcnow()
        user.last_login_ip = get_client_ip()
        user.save()
        
        # Log successful login
        SecurityAudit.audit_login_attempt(
            str(user._id), True, get_client_ip(),
            request.headers.get('User-Agent', '')
        )
        
        # Create tokens
        token_expires = timedelta(days=7) if data.get('remember_me') else None
        access_token = create_access_token(
            identity=str(user._id),
            fresh=True,
            expires_delta=token_expires
        )
        refresh_token = create_refresh_token(identity=str(user._id))
        
        # Get user's primary account
        primary_account = Account.get_primary_account(user._id)
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'data': {
                'user': user.json(),
                'access_token': access_token,
                'refresh_token': refresh_token,
                'primary_account': primary_account.json() if primary_account else None
            }
        })
        
    except ValidationError as e:
        return jsonify({
            'success': False,
            'message': 'Validation error',
            'errors': e.messages
        }), 400
    except Exception as e:
        import traceback
        current_app.logger.error(f"Login error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': 'Login failed. Please try again.'
        }), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user or not user.is_active:
            return jsonify({
                'success': False,
                'message': 'Invalid user or account deactivated'
            }), 401
        
        # Create new access token
        new_access_token = create_access_token(
            identity=current_user_id,
            fresh=False
        )
        
        return jsonify({
            'success': True,
            'data': {
                'access_token': new_access_token
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Token refresh failed'
        }), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout user and revoke token"""
    try:
        current_user_id = get_jwt_identity()
        jti = get_jwt()['jti']
        
        # Add token to blacklist
        revoke_token(jti)
        
        # Log logout event
        log_security_event('logout', current_user_id, {
            'token_jti': jti
        })
        
        return jsonify({
            'success': True,
            'message': 'Successfully logged out'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Logout failed'
        }), 500

@auth_bp.route('/password-reset-request', methods=['POST'])
@limiter.limit("3 per minute")
def password_reset_request():
    """Request password reset"""
    try:
        # Validate request data
        schema = PasswordResetRequestSchema()
        data = schema.load(request.get_json() or {})
        
        # Find user
        user = User.find_one({'email': data['email'].lower()})
        if user:
            # Generate reset token
            reset_token = user.generate_reset_token()
            
            # Create reset link (in production, this would be a frontend URL)
            reset_link = f"{current_app.config['CLIENT_URL']}/reset-password?token={reset_token}"
            
            # Send reset email
            NotificationService.send_password_reset_email(
                user.email,
                user.first_name,
                reset_link
            )
            
            # Log security event
            log_security_event('password_reset_requested', str(user._id), {
                'email': user.email
            })
        
        # Always return success to prevent email enumeration
        return jsonify({
            'success': True,
            'message': 'If the email exists, a password reset link has been sent.'
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
            'message': 'Password reset request failed'
        }), 500

@auth_bp.route('/password-reset', methods=['POST'])
@limiter.limit("3 per minute")
def password_reset():
    """Reset password with token"""
    try:
        # Validate request data
        schema = PasswordResetSchema()
        data = schema.load(request.get_json() or {})
        
        # Validate password strength
        try:
            validate_password_strength(data['new_password'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Verify reset token
        user = User.verify_reset_token(data['token'])
        if not user:
            return jsonify({
                'success': False,
                'message': 'Invalid or expired reset token'
            }), 400
        
        # Update password
        user.set_password(data['new_password'])
        user.reset_token = None
        user.reset_token_expires = None
        user.save()
        
        # Send security alert
        NotificationService.send_security_alert(
            user.email,
            user.first_name,
            'Password Changed',
            {'action': 'Password was successfully reset using reset token'}
        )
        
        # Log security event
        log_security_event('password_reset_completed', str(user._id))
        
        return jsonify({
            'success': True,
            'message': 'Password reset successful'
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
            'message': 'Password reset failed'
        }), 500

@auth_bp.route('/change-password', methods=['POST'])
@jwt_required(fresh=True)

def change_password():
    """Change password for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Validate request data
        schema = ChangePasswordSchema()
        data = schema.load(request.get_json() or {})
        
        # Verify current password
        if not user.check_password(data['current_password']):
            return jsonify({
                'success': False,
                'message': 'Current password is incorrect'
            }), 401
        
        # Validate new password strength
        try:
            validate_password_strength(data['new_password'])
        except ValidationError as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        
        # Check if new password is different from current
        if user.check_password(data['new_password']):
            return jsonify({
                'success': False,
                'message': 'New password must be different from current password'
            }), 400
        
        # Update password
        user.set_password(data['new_password'])
        user.save()
        
        # Send security alert
        NotificationService.send_security_alert(
            user.email,
            user.first_name,
            'Password Changed',
            {'action': 'Password was successfully changed'}
        )
        
        # Log security event
        log_security_event('password_changed', str(user._id))
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
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
            'message': 'Password change failed'
        }), 500

@auth_bp.route('/verify-token', methods=['GET'])
@jwt_required()
def verify_token():
    """Verify if token is valid and return user info"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user or not user.is_active:
            return jsonify({
                'success': False,
                'message': 'Invalid token or user deactivated'
            }), 401
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.json(),
                'valid': True
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Token verification failed'
        }), 401

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current authenticated user information"""
    try:
        current_user_id = get_jwt_identity()
        user = User.find_by_id(current_user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Get user's accounts
        accounts = Account.get_user_accounts(user._id)
        
        return jsonify({
            'success': True,
            'data': {
                'user': user.json(),
                'accounts': [account.json() for account in accounts]
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to get user information'
        }), 500
