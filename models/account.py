from datetime import datetime
from bson import ObjectId
import random
from . import BaseModel
from extensions import mongo

class Account(BaseModel):
    """Account model class"""
    
    collection_name = "accounts"
    
    def __init__(self, **kwargs):
        """Initialize Account"""
        super().__init__(**kwargs)
        
        # Generate account number if not provided
        if 'account_number' not in self.data or not self.data.get('account_number'):
            self.data['account_number'] = self.generate_account_number()
        
        # Set default values
        if 'account_type' not in self.data:
            self.data['account_type'] = 'checking'
        if 'balance' not in self.data:
            self.data['balance'] = 0.0
        if 'available_balance' not in self.data:
            self.data['available_balance'] = self.data['balance']
        if 'currency' not in self.data:
            self.data['currency'] = 'INR'
        if 'is_active' not in self.data:
            self.data['is_active'] = True
        if 'is_primary' not in self.data:
            self.data['is_primary'] = False
        if 'daily_transaction_limit' not in self.data:
            self.data['daily_transaction_limit'] = 10000.0
        if 'monthly_transaction_limit' not in self.data:
            self.data['monthly_transaction_limit'] = 50
        if 'overdraft_limit' not in self.data:
            self.data['overdraft_limit'] = 0.0
        if 'is_frozen' not in self.data:
            self.data['is_frozen'] = False
        if 'freeze_reason' not in self.data:
            self.data['freeze_reason'] = 'none'
    
    def generate_account_number(self):
        """Generate a unique account number"""
        while True:
            # Generate 12-digit account number
            account_number = ''.join([str(random.randint(0, 9)) for _ in range(12)])
            
            # Check if account number already exists
            existing_account = Account.find_one({'account_number': account_number})
            if not existing_account:
                return account_number
    
    def get_masked_account_number(self):
        """Get masked account number for display"""
        account_number = getattr(self, 'account_number', None)
        if not account_number or not isinstance(account_number, str):
            return "****"
        return f"****{account_number[-4:]}"
    
    def can_transact(self, amount, transaction_type='debit'):
        """Check if transaction is allowed"""
        if self.is_frozen:
            return {'allowed': False, 'reason': 'Account is frozen'}
        
        if not self.is_active:
            return {'allowed': False, 'reason': 'Account is inactive'}
        
        if transaction_type == 'debit':
            overdraft = getattr(self, 'overdraft_limit', None) or 0
            available_amount = self.balance + overdraft
            if amount > available_amount:
                return {'allowed': False, 'reason': 'Insufficient funds'}
            
            if amount > self.daily_transaction_limit:
                return {'allowed': False, 'reason': 'Exceeds daily transaction limit'}
        
        return {'allowed': True}
    
    def freeze_account(self, reason='user_request'):
        """Freeze the account"""
        self.is_frozen = True
        self.freeze_reason = reason
        self.freeze_date = datetime.utcnow()
        self.save()
    
    def unfreeze_account(self):
        """Unfreeze the account"""
        self.is_frozen = False
        self.freeze_reason = 'none'
        self.freeze_date = None
        self.save()
    
    def update_balance(self, amount, transaction_type='debit'):
        """Update account balance"""

        amount = float(amount)
         
        if transaction_type == 'debit':
            self.balance -= amount
        else:
            self.balance += amount
        
        # Ensure balance precision (2 decimal places)
        self.balance = round(self.balance, 2)
        self.available_balance = self.balance
        self.last_transaction_date = datetime.utcnow()
        self.save()
    
    def json(self, exclude_fields=None):
        """Convert account to JSON"""
        data = self.to_dict(exclude_fields=exclude_fields)
        data['masked_account_number'] = self.get_masked_account_number()
        data['is_overdrawn'] = self.balance < 0
        
        if hasattr(self, 'overdraft_limit') and self.overdraft_limit:
            data['available_credit'] = self.balance + self.overdraft_limit
        
        return data
    
    @classmethod
    def get_user_accounts(cls, user_id, active_only=True):
        """Get all accounts for a user"""
        query = {'user_id': ObjectId(user_id)}
        if active_only:
            query['is_active'] = True
        
        return cls.find(query, sort=[('is_primary', -1), ('created_at', -1)])
    
    @classmethod
    def get_primary_account(cls, user_id):
        """Get user's primary account"""
        return cls.find_one({
            'user_id': ObjectId(user_id),
            'is_primary': True,
            'is_active': True
        })
    
    def set_as_primary(self):
        """Set this account as primary and remove primary status from others"""
        # Remove primary status from other accounts
        collection = self.get_collection()
        collection.update_many(
            {'user_id': self.user_id, '_id': {'$ne': self._id}},
            {'$set': {'is_primary': False}}
        )
        
        # Set this account as primary
        self.is_primary = True
        self.save()
