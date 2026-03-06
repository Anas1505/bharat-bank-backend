from datetime import datetime, timedelta
from bson import ObjectId
from marshmallow import Schema, fields, validate, post_load, ValidationError
from . import BaseModel, validate_email, validate_phone, hash_password, check_password
from extensions import mongo
import bcrypt
import re

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
    
    def set_password(self, password):
        """Set a new password for user"""
        self.password = hash_password(password)
    
    def json(self, exclude_fields=None):
        """Convert user to JSON"""
        exclude_fields = exclude_fields or ['password', 'reset_token', 'reset_token_expires']
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
