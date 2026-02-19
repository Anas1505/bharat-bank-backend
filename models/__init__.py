from datetime import datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from extensions import mongo
import bcrypt
import re

class BaseModel:
    """Base model class with common functionality"""
    
    collection_name = None
    
    def __init__(self, **kwargs):
        self.data = kwargs
        if '_id' not in self.data:
            self.data['_id'] = ObjectId()
        if 'created_at' not in self.data:
            self.data['created_at'] = datetime.utcnow()
        if 'updated_at' not in self.data:
            self.data['updated_at'] = datetime.utcnow()
    
    @classmethod
    def get_collection(cls):
        """Get MongoDB collection for this model"""
        if not cls.collection_name:
            raise NotImplementedError("collection_name must be defined in subclass")
        return mongo.db[cls.collection_name]
    
    def save(self):
        """Save document to database"""
        self.data['updated_at'] = datetime.utcnow()
        collection = self.get_collection()
        
        if self.exists():
            # Update existing document
            result = collection.update_one(
                {'_id': self.data['_id']},
                {'$set': self.data}
            )
            return result.modified_count > 0
        else:
            # Insert new document
            try:
                result = collection.insert_one(self.data)
                return result.inserted_id == self.data['_id']
            except DuplicateKeyError as e:
                raise ValueError(f"Duplicate key error: {str(e)}")
    
    def delete(self):
        """Delete document from database"""
        collection = self.get_collection()
        result = collection.delete_one({'_id': self.data['_id']})
        return result.deleted_count > 0
    
    def exists(self):
        """Check if document exists in database"""
        collection = self.get_collection()
        return collection.find_one({'_id': self.data['_id']}) is not None
    
    @classmethod
    def find_by_id(cls, doc_id):
        """Find document by ID"""
        if isinstance(doc_id, str):
            doc_id = ObjectId(doc_id)
        
        collection = cls.get_collection()
        doc = collection.find_one({'_id': doc_id})
        
        if doc:
            return cls(**doc)
        return None
    
    @classmethod
    def find_one(cls, query):
        """Find single document matching query"""
        collection = cls.get_collection()
        doc = collection.find_one(query)
        
        if doc:
            return cls(**doc)
        return None
    
    @classmethod
    def find(cls, query=None, limit=None, skip=None, sort=None):
        """Find multiple documents matching query"""
        collection = cls.get_collection()
        cursor = collection.find(query or {})
        
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        
        return [cls(**doc) for doc in cursor]
    
    @classmethod
    def count_documents(cls, query=None):
        """Count documents matching query"""
        collection = cls.get_collection()
        return collection.count_documents(query or {})
    
    def to_dict(self, exclude_fields=None):
        """Convert document to dictionary"""
        exclude_fields = exclude_fields or []
        result = {}
        
        for key, value in self.data.items():
            if key in exclude_fields:
                continue
                
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        
        return result
    
    def __getattr__(self, name):
        """Allow accessing data fields as attributes"""
        if name in self.data:
            return self.data[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __setattr__(self, name, value):
        """Allow setting data fields as attributes"""
        if name == 'data':
            super().__setattr__(name, value)
        else:
            if not hasattr(self, 'data'):
                super().__setattr__(name, value)
            else:
                self.data[name] = value

class ValidationError(Exception):
    """Custom validation error"""
    pass

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Validate phone number format"""
    pattern = r'^\d{10,15}$'
    return re.match(pattern, phone) is not None

def hash_password(password):
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Check password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
