import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from flask import request, current_app
from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from extensions import blacklisted_tokens
import ipaddress
import re

def generate_secure_token(length=32):
    """Generate a cryptographically secure random token"""
    return secrets.token_urlsafe(length)

def hash_sensitive_data(data):
    """Hash sensitive data using SHA-256"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def mask_sensitive_info(text, mask_char='*', visible_chars=4):
    """Mask sensitive information like account numbers, showing only last few characters"""
    if not text or len(text) <= visible_chars:
        return text
    
    return mask_char * (len(text) - visible_chars) + text[-visible_chars:]

def get_client_ip():
    """Get client IP address, handling proxy headers"""
    # Check for forwarded IP first (in case of reverse proxy)
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    elif request.environ.get('HTTP_X_REAL_IP'):
        return request.environ['HTTP_X_REAL_IP']
    else:
        return request.environ.get('REMOTE_ADDR')

def is_safe_ip(ip_address):
    """Check if IP address is from a safe range (not from known malicious ranges)"""
    try:
        ip = ipaddress.ip_address(ip_address)
        
        # Block known private ranges that shouldn't be accessing externally
        private_ranges = [
            ipaddress.ip_network('10.0.0.0/8'),
            ipaddress.ip_network('172.16.0.0/12'),
            ipaddress.ip_network('192.168.0.0/16'),
        ]
        
        # Allow localhost for development
        if ip.is_loopback:
            return True
            
        # Check if IP is in private range (might be suspicious for external access)
        for private_range in private_ranges:
            if ip in private_range:
                return False
        
        return True
    except ValueError:
        return False

def log_security_event(event_type, user_id=None, details=None):
    """Log security events for monitoring"""
    event_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'ip_address': get_client_ip(),
        'user_agent': request.headers.get('User-Agent', ''),
        'user_id': user_id,
        'details': details or {}
    }
    
    # In a production environment, this would be sent to a logging service
    # For now, we'll just print to console
    print(f"SECURITY EVENT: {event_data}")
    return event_data

def check_rate_limit_exceeded(key, max_attempts=5, window_minutes=15):
    """
    Check if rate limit has been exceeded for a given key
    This is a simple in-memory implementation
    In production, use Redis or similar
    """
    # This would be implemented with a proper cache in production
    # For now, return False (no rate limiting)
    return False

def validate_request_signature(signature, payload, secret_key):
    """Validate webhook or API request signature"""
    expected_signature = hashlib.sha256(
        (payload + secret_key).encode('utf-8')
    ).hexdigest()
    
    return secrets.compare_digest(signature, expected_signature)

def encrypt_sensitive_field(data, key=None):
    """Encrypt sensitive field data (placeholder for actual encryption)"""
    # In production, use proper encryption like AES
    # This is a simple base64 encoding for demo purposes
    import base64
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.b64encode(data).decode('utf-8')

def decrypt_sensitive_field(encrypted_data, key=None):
    """Decrypt sensitive field data (placeholder for actual decryption)"""
    # In production, use proper decryption
    import base64
    try:
        return base64.b64decode(encrypted_data.encode('utf-8')).decode('utf-8')
    except Exception:
        return encrypted_data

def check_password_complexity(password):
    """Check password complexity and return score (0-100)"""
    score = 0
    
    # Length bonus
    if len(password) >= 8:
        score += 20
    if len(password) >= 12:
        score += 10
    if len(password) >= 16:
        score += 10
    
    # Character variety bonus
    if re.search(r'[a-z]', password):
        score += 10
    if re.search(r'[A-Z]', password):
        score += 10
    if re.search(r'\d', password):
        score += 10
    if re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
        score += 15
    
    # Pattern penalties
    if re.search(r'(.)\1{2,}', password):  # Repeated characters
        score -= 10
    if re.search(r'(012|123|234|345|456|567|678|789|890)', password):  # Sequential numbers
        score -= 5
    if re.search(r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):  # Sequential letters
        score -= 5
    
    # Common patterns penalty
    common_patterns = ['password', '123456', 'qwerty', 'admin', 'user']
    for pattern in common_patterns:
        if pattern.lower() in password.lower():
            score -= 20
    
    return max(0, min(100, score))

def generate_otp(length=6):
    """Generate a numeric OTP"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(length)])

def verify_device_fingerprint(fingerprint):
    """Verify device fingerprint for additional security"""
    # This would implement device fingerprinting logic
    # For now, just check if fingerprint is provided and has reasonable format
    if not fingerprint or len(fingerprint) < 32:
        return False
    
    # Check if it's a valid hex string
    try:
        int(fingerprint, 16)
        return True
    except ValueError:
        return False

class SecurityAudit:
    """Security audit helper class"""
    
    @staticmethod
    def audit_login_attempt(user_id, success, ip_address, user_agent):
        """Audit login attempt"""
        event_type = 'login_success' if success else 'login_failure'
        details = {
            'ip_address': ip_address,
            'user_agent': user_agent,
            'timestamp': datetime.utcnow().isoformat()
        }
        return log_security_event(event_type, user_id, details)
    
    @staticmethod
    def audit_transaction(transaction_id, user_id, amount, transaction_type):
        """Audit transaction"""
        details = {
            'transaction_id': transaction_id,
            'amount': amount,
            'type': transaction_type
        }
        return log_security_event('transaction_created', user_id, details)
    
    @staticmethod
    def audit_account_change(user_id, change_type, account_id=None):
        """Audit account changes"""
        details = {
            'change_type': change_type,
            'account_id': account_id
        }
        return log_security_event('account_change', user_id, details)

def require_fresh_token(f):
    """Decorator to require fresh JWT token for sensitive operations"""
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request(fresh=True)
        return f(*args, **kwargs)
    return decorated

def check_suspicious_activity(user_id, activity_type, **kwargs):
    """Check for suspicious activity patterns"""
    # This would implement more sophisticated fraud detection
    # For now, just basic checks
    
    suspicious_indicators = []
    
    # Check for unusual transaction amounts
    if activity_type == 'transaction' and 'amount' in kwargs:
        amount = kwargs['amount']
        if amount > 50000:  # Large transaction
            suspicious_indicators.append('large_amount')
    
    # Check for unusual timing
    current_hour = datetime.utcnow().hour
    if current_hour < 6 or current_hour > 22:
        suspicious_indicators.append('unusual_time')
    
    # Check for rapid successive operations
    if activity_type in ['transaction', 'login'] and 'last_activity_time' in kwargs:
        last_activity = kwargs['last_activity_time']
        if isinstance(last_activity, datetime):
            time_diff = datetime.utcnow() - last_activity
            if time_diff.total_seconds() < 60:  # Less than 1 minute
                suspicious_indicators.append('rapid_succession')
    
    return {
        'is_suspicious': len(suspicious_indicators) > 0,
        'indicators': suspicious_indicators,
        'risk_score': len(suspicious_indicators) * 25  # Simple scoring
    }
