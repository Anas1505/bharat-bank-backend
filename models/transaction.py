from datetime import datetime
from bson import ObjectId
import random
import string
from . import BaseModel
from .account import Account

class Transaction(BaseModel):
    """Transaction model class"""
    
    collection_name = "transactions"
    
    TRANSACTION_TYPES = [
        'deposit', 'withdrawal', 'transfer', 'payment', 
        'fee', 'interest', 'refund', 'reversal'
    ]
    
    TRANSACTION_STATUS = ['pending', 'completed', 'failed', 'cancelled', 'reversed']
    
    CATEGORIES = [
        'food_dining', 'shopping', 'transportation', 'entertainment',
        'healthcare', 'utilities', 'groceries', 'education', 'travel',
        'fitness', 'insurance', 'investment', 'salary', 'business', 'other'
    ]
    
    def __init__(self, **kwargs):
        """Initialize Transaction"""
        super().__init__(**kwargs)
        
        # Generate transaction ID if not provided
        if 'transaction_id' not in self.data:
            self.data['transaction_id'] = self.generate_transaction_id()
        
        # Set default values
        if 'status' not in self.data:
            self.data['status'] = 'pending'
        if 'category' not in self.data:
            self.data['category'] = 'other'
        if 'currency' not in self.data:
            self.data['currency'] = 'USD'
        if 'method' not in self.data:
            self.data['method'] = 'mobile_app'
        if 'fees' not in self.data:
            self.data['fees'] = {'amount': 0.0, 'type': 'none'}
        if 'amount' in self.data:
            self.data['amount'] = float(self.data['amount'])
    
    def generate_transaction_id(self):
        """Generate a unique transaction ID"""
        timestamp = str(int(datetime.utcnow().timestamp()))
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"TXN{timestamp}{random_part}"
    
    def calculate_risk_score(self):
        """Calculate risk score for the transaction"""
        score = 0
        
        # High amount transactions
        if self.amount > 10000:
            score += 30
        elif self.amount > 5000:
            score += 20
        elif self.amount > 1000:
            score += 10
        
        # Off-hours transactions (before 6 AM or after 10 PM)
        hour = datetime.utcnow().hour
        if hour < 6 or hour > 22:
            score += 15
        
        # International transactions
        if self.currency != 'USD':
            score += 25
        
        # Weekend transactions
        weekday = datetime.utcnow().weekday()
        if weekday >= 5:  # Saturday = 5, Sunday = 6
            score += 10
        
        # Ensure score doesn't exceed 100
        score = min(score, 100)
        
        # Update security fields
        if 'security' not in self.data:
            self.data['security'] = {}
        
        self.data['security']['risk_score'] = score
        
        # Flag high-risk transactions
        if score > 70:
            self.data['security']['requires_review'] = True
            if 'fraud_flags' not in self.data['security']:
                self.data['security']['fraud_flags'] = []
            
            if 'high_risk_score' not in self.data['security']['fraud_flags']:
                self.data['security']['fraud_flags'].append('high_risk_score')
        
        return score
    
    def process_transaction(self):
        """Process the transaction and update account balances"""
        if self.status != 'pending':
            raise ValueError("Only pending transactions can be processed")
        
        try:
            # Calculate risk score
            self.calculate_risk_score()
            
            # Get accounts
            from_account = None
            to_account = None
            
            if hasattr(self, 'from_account_id') and self.from_account_id:
                from_account = Account.find_by_id(self.from_account_id)
            
            if hasattr(self, 'to_account_id') and self.to_account_id:
                to_account = Account.find_by_id(self.to_account_id)
            
            # Process based on transaction type
            if self.type in ['withdrawal', 'payment', 'fee']:
                if not from_account:
                    raise ValueError("From account is required for this transaction type")
                
                # Check if transaction is allowed
                can_transact = from_account.can_transact(self.amount, 'debit')
                if not can_transact['allowed']:
                    self.status = 'failed'
                    self.data['failure_reason'] = can_transact['reason']
                    self.save()
                    return False
                
                # Update from account balance
                from_account.update_balance(self.amount, 'debit')
                self.data['balance_after'] = from_account.balance
            
            elif self.type == 'deposit':
                if not to_account:
                    raise ValueError("To account is required for deposit transactions")
                
                # Update to account balance
                to_account.update_balance(self.amount, 'credit')
                self.data['balance_after'] = to_account.balance
            
            elif self.type == 'transfer':
                if not from_account or not to_account:
                    raise ValueError("Both from and to accounts are required for transfers")
                
                # Check if transaction is allowed
                can_transact = from_account.can_transact(self.amount, 'debit')
                if not can_transact['allowed']:
                    self.status = 'failed'
                    self.data['failure_reason'] = can_transact['reason']
                    self.save()
                    return False
                
                # Update both account balances
                from_account.update_balance(self.amount, 'debit')
                to_account.update_balance(self.amount, 'credit')
                self.data['balance_after'] = from_account.balance
            
            # Mark transaction as completed
            self.status = 'completed'
            if 'metadata' not in self.data:
                self.data['metadata'] = {}
            self.data['metadata']['processing_time'] = datetime.utcnow()
            
            self.save()
            return True
            
        except Exception as e:
            self.status = 'failed'
            self.data['failure_reason'] = str(e)
            self.save()
            return False
    
    def reverse_transaction(self, reason="User request"):
        """Reverse a completed transaction"""
        if self.status != 'completed':
            raise ValueError("Only completed transactions can be reversed")
        
        # Create reversal transaction
        reversal_data = {
            'from_account_id': getattr(self, 'to_account_id', None),
            'to_account_id': getattr(self, 'from_account_id', None),
            'user_id': self.user_id,
            'type': 'reversal',
            'amount': self.amount,
            'currency': self.currency,
            'description': f"Reversal of {self.description} - {reason}",
            'category': self.category,
            'status': 'completed',
            'method': self.method,
            'metadata': {
                'original_transaction_id': str(self._id),
                'reversal_reason': reason
            }
        }
        
        reversal = Transaction(**reversal_data)
        
        # Process the reversal (update balances)
        if reversal.process_transaction():
            # Mark original transaction as reversed
            self.status = 'reversed'
            self.save()
            return reversal
        
        return None
    
    def json(self, exclude_fields=None):
        """Convert transaction to JSON"""
        data = self.to_dict(exclude_fields=exclude_fields)
        
        # Add calculated fields
        data['formatted_amount'] = f"{self.currency} {self.amount:.2f}"
        data['is_debit'] = self.type in ['withdrawal', 'transfer', 'payment', 'fee']
        data['is_credit'] = self.type in ['deposit', 'interest', 'refund']
        
        # Add total amount including fees
        fees_amount = self.data.get('fees', {}).get('amount', 0)
        data['total_amount'] = self.amount + fees_amount
        
        return data
    
    @classmethod
    def get_user_transactions(cls, user_id, limit=50, skip=0, account_id=None):
        """Get transactions for a user"""
        query = {'user_id': ObjectId(user_id)}
        
        if account_id:
            query['$or'] = [
                {'from_account_id': ObjectId(account_id)},
                {'to_account_id': ObjectId(account_id)}
            ]
        
        return cls.find(
            query,
            limit=limit,
            skip=skip,
            sort=[('created_at', -1)]
        )
    
    @classmethod
    def get_account_transactions(cls, account_id, limit=50, skip=0):
        """Get transactions for a specific account"""
        query = {
            '$or': [
                {'from_account_id': ObjectId(account_id)},
                {'to_account_id': ObjectId(account_id)}
            ]
        }
        
        return cls.find(
            query,
            limit=limit,
            skip=skip,
            sort=[('created_at', -1)]
        )
    
    @classmethod
    def get_pending_transactions(cls, user_id=None):
        """Get pending transactions"""
        query = {'status': 'pending'}
        if user_id:
            query['user_id'] = ObjectId(user_id)
        
        return cls.find(query, sort=[('created_at', 1)])
    
    def get_transaction_summary(self):
        """Get a summary of the transaction for notifications"""
        summary = {
            'transaction_id': self.transaction_id,
            'amount': self.amount,
            'currency': self.currency,
            'type': self.type,
            'description': self.description,
            'status': self.status,
            'date': self.created_at.isoformat()
        }
        
        if hasattr(self, 'balance_after'):
            summary['balance_after'] = self.balance_after
        
        return summary
