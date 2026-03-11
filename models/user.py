from datetime import datetime, timedelta
from bson import ObjectId
from marshmallow import Schema, fields, validate, post_load, ValidationError
from . import BaseModel, validate_email, validate_phone, hash_password, check_password
from extensions import mongo
import bcrypt
import re

# Transaction PIN settings
PIN_MAX_ATTEMPTS = 3
PIN_LOCKOUT_MINUTES = 15

class User(BaseModel):
    """User model class"""
    
    collection_name = "users"
    
    def __init__(self, **kwargs):
        """Initialize User with hashed password"""
        super().__init__(**kwargs)
        if 'password' in kwargs:
            # Only hash if password is not already hashed (bcrypt hashes start with $2a$, $2b$, or $2y$)
            password = kwargs['password']
            if not (isinstance(password, str) and password.startswith('$2')):
                self.data['password'] = hash_password(password)
            else:
                # Password is already hashed, use it as-is
                self.data['password'] = password
        
        # Ensure default values for transaction PIN security fields
        if 'pin_attempts' not in self.data:
            self.data['pin_attempts'] = 0
        if 'pin_locked_until' not in self.data:
            self.data['pin_locked_until'] = None

        # High-level security/consent metadata
        if 'transaction_pin_set' not in self.data:
            # Consider PIN set if a hash already exists (for legacy users)
            existing_hash = self.data.get('transaction_pin_hash')
            self.data['transaction_pin_set'] = bool(existing_hash)
        if 'terms_accepted' not in self.data:
            # Will be set to True during registration when terms are accepted
            self.data['terms_accepted'] = False
        # Normalize password change metadata
        if 'password_changed_at' in self.data and 'last_password_change' not in self.data:
            self.data['last_password_change'] = self.data['password_changed_at']
    
    def check_password(self, password):
        """Check password against stored hash"""
        if not password:
            return False
        stored_hash = self.password
        if not stored_hash:
            return False
        try:
            return check_password(password, stored_hash)
        except Exception:
            return False

    # Transaction PIN helpers
    def set_transaction_pin(self, pin: str):
        """Set or update the user's 4-digit transaction PIN."""
        if not pin:
            raise ValueError("Transaction PIN is required")
        pin_str = str(pin).strip()
        if not re.fullmatch(r"\d{4}", pin_str):
            raise ValueError("Transaction PIN must be exactly 4 digits")

        # Reuse the same hashing mechanism as passwords (bcrypt)
        self.transaction_pin_hash = hash_password(pin_str)
        # Reset attempts and lock status whenever PIN is (re)set
        self.pin_attempts = 0
        self.pin_locked_until = None
        self.transaction_pin_set = True

    def check_transaction_pin(self, pin: str) -> bool:
        """Verify the provided PIN against the stored hash."""
        if not pin:
            return False

        stored_hash = getattr(self, "transaction_pin_hash", None)
        if not stored_hash:
            return False

        try:
            return check_password(str(pin).strip(), stored_hash)
        except Exception:
            return False

    def is_pin_locked(self) -> bool:
        """Return True if the transaction PIN is currently locked."""
        locked_until = getattr(self, "pin_locked_until", None)
        if not locked_until:
            return False
        try:
            # In case pin_locked_until is stored as string, try parsing
            if isinstance(locked_until, str):
                try:
                    locked_until_dt = datetime.fromisoformat(locked_until)
                except ValueError:
                    return False
            else:
                locked_until_dt = locked_until
            return locked_until_dt > datetime.utcnow()
        except Exception:
            return False

    def set_password(self, password):
        """Set a new password for user"""
        self.password = hash_password(password)
        now = datetime.utcnow()
        self.password_changed_at = now
        self.last_password_change = now
    
    def json(self, exclude_fields=None):
        """Convert user to JSON"""
        exclude_fields = exclude_fields or [
            'password',
            'reset_token',
            'reset_token_expires',
            'transaction_pin_hash',
            'pin_attempts',
            'pin_locked_until',
        ]
        return self.to_dict(exclude_fields=exclude_fields)
    
    def generate_reset_token(self):
        """Generate password reset token"""
        token = bcrypt.gensalt().decode('utf-8')
        self.reset_token = token
        self.reset_token_expires = datetime.utcnow() + timedelta(minutes=30) # 30 mins expiry
        self.save()
        return token
    
    @staticmethod
    def verify_reset_token(token):
        """Verify password reset token"""
        user = User.find_one({'reset_token': token})
        if user and user.reset_token_expires > datetime.utcnow():
            return user
        return None

class UserSchema(Schema):
    """Schema for user validation"""
    
    first_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    last_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    email = fields.Email(required=True, validate=validate.Email())
    phone = fields.Str(validate=validate_phone)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))
    date_of_birth = fields.Date(required=True)
    
    @post_load
    def make_user(self, data, **kwargs):
        return User(**data)

    @staticmethod
    def validate_email(email):
        if not validate_email(email):
            raise ValidationError("Invalid email format")

    @staticmethod
    def validate_phone(phone):
        if not validate_phone(phone):
            raise ValidationError("Invalid phone number format")
