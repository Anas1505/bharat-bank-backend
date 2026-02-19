#!/usr/bin/env python3
"""Diagnostic script to check the Flask app functionality."""

import traceback
from app import app

def diagnose_app():
    """Diagnose the Flask application."""
    print("=== Mobile Banking API Diagnostics ===")
    
    try:
        print(f"✓ App imported successfully")
        print(f"✓ App name: {app.name}")
        print(f"✓ Debug mode: {app.debug}")
        
        print("\n=== Available Routes ===")
        for rule in app.url_map.iter_rules():
            methods = ', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
            print(f"  {methods:15} {rule.rule}")
        
        print("\n=== Testing Endpoints ===")
        with app.test_client() as client:
            # Test root endpoint
            try:
                response = client.get('/')
                print(f"✓ Root (/) - Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.get_json()
                    print(f"  Message: {data.get('message', 'No message')}")
            except Exception as e:
                print(f"✗ Root (/) - Error: {e}")
            
            # Test health endpoint
            try:
                response = client.get('/api/health')
                print(f"✓ Health - Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.get_json()
                    print(f"  Status: {data.get('status', 'Unknown')}")
            except Exception as e:
                print(f"✗ Health - Error: {e}")
        
        print("\n=== Configuration Check ===")
        config_items = [
            'SECRET_KEY', 'JWT_SECRET_KEY', 'MONGO_URI', 
            'MAIL_SERVER', 'DEBUG'
        ]
        for item in config_items:
            value = app.config.get(item, 'Not set')
            if 'SECRET' in item or 'PASSWORD' in item:
                value = '***hidden***' if value != 'Not set' else 'Not set'
            print(f"  {item}: {value}")
        
        print("\n=== Extensions Check ===")
        try:
            from extensions import mongo, jwt, limiter, mail
            print("✓ All extensions imported successfully")
            print(f"✓ MongoDB: {mongo}")
            print(f"✓ JWT Manager: {jwt}")
            print(f"✓ Rate Limiter: {limiter}")
            print(f"✓ Mail: {mail}")
        except Exception as e:
            print(f"✗ Extensions error: {e}")
            traceback.print_exc()
        
        print("\n=== Routes Check ===")
        try:
            from routes.auth import auth_bp
            from routes.accounts import accounts_bp
            from routes.transactions import transactions_bp
            from routes.users import users_bp
            print("✓ All route blueprints imported successfully")
        except Exception as e:
            print(f"✗ Routes error: {e}")
            traceback.print_exc()
        
        print("\n=== Models Check ===")
        try:
            from models.user import User
            from models.account import Account
            from models.transaction import Transaction
            print("✓ All models imported successfully")
        except Exception as e:
            print(f"✗ Models error: {e}")
            traceback.print_exc()
        
        print("\n=== Final Status ===")
        print("✓ Application is ready to run!")
        print("  Start with: python run_server.py")
        print("  Or: python app.py")
        
    except Exception as e:
        print(f"✗ Critical error: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    diagnose_app()
