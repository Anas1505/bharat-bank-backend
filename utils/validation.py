import re
from datetime import datetime, timedelta
from marshmallow import ValidationError

def validate_password_strength(password):
    """
    Validate password strength requirements:
    - At least 8 characters
    - Contains uppercase letter
    - Contains lowercase letter
    - Contains digit
    - Contains special character
    """
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter")
    
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter")
    
    if not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one digit")
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValidationError("Password must contain at least one special character")
    
    return True

def validate_account_number(account_number):
    """Validate account number format"""
    if not account_number or not isinstance(account_number, str):
        return False
    
    # Account number should be 12 digits
    if not re.match(r'^\d{12}$', account_number):
        return False
    
    return True

def validate_transaction_amount(amount):
    """Validate transaction amount"""
    if not isinstance(amount, (int, float)):
        raise ValidationError("Amount must be a number")
    
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero")
    
    if amount > 100000:  # Max transaction limit
        raise ValidationError("Amount exceeds maximum transaction limit")
    
    # Check for reasonable decimal places (max 2)
    if isinstance(amount, float):
        decimal_places = len(str(amount).split('.')[1]) if '.' in str(amount) else 0
        if decimal_places > 2:
            raise ValidationError("Amount cannot have more than 2 decimal places")
    
    return True

def validate_date_range(start_date, end_date):
    """Validate date range for queries"""
    if not isinstance(start_date, datetime):
        raise ValidationError("Start date must be a datetime object")
    
    if not isinstance(end_date, datetime):
        raise ValidationError("End date must be a datetime object")
    
    if start_date >= end_date:
        raise ValidationError("Start date must be before end date")
    
    # Check if date range is not too large (max 1 year)
    if end_date - start_date > timedelta(days=365):
        raise ValidationError("Date range cannot exceed 365 days")
    
    return True

def validate_currency_code(currency):
    """Validate currency code"""
    valid_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'CNY']
    
    if not currency or currency not in valid_currencies:
        raise ValidationError(f"Currency must be one of: {', '.join(valid_currencies)}")
    
    return True

def sanitize_input(text):
    """Sanitize text input to prevent XSS and injection attacks"""
    if not isinstance(text, str):
        return text
    
    # Remove potentially dangerous characters
    text = re.sub(r'[<>"\']', '', text)
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    return text.strip()

def validate_pin(pin):
    """Validate PIN format"""
    if not pin or not isinstance(pin, str):
        raise ValidationError("PIN is required")
    
    if not re.match(r'^\d{4}$', pin):
        raise ValidationError("PIN must be exactly 4 digits")
    
    return True

def validate_sort_code(sort_code):
    """Validate UK sort code format"""
    if not sort_code:
        return True  # Optional field
    
    if not re.match(r'^\d{2}-\d{2}-\d{2}$', sort_code):
        raise ValidationError("Sort code must be in format XX-XX-XX")
    
    return True

def validate_iban(iban):
    """Basic IBAN validation"""
    if not iban:
        return True  # Optional field
    
    # Remove spaces and convert to uppercase
    iban = iban.replace(' ', '').upper()
    
    # Basic length check (IBAN should be between 15-34 characters)
    if not (15 <= len(iban) <= 34):
        raise ValidationError("IBAN must be between 15-34 characters")
    
    # Should start with 2 letters followed by 2 digits
    if not re.match(r'^[A-Z]{2}\d{2}', iban):
        raise ValidationError("IBAN must start with 2 letters and 2 digits")
    
    return True
