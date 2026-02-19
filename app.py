from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
import os
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import configurations and extensions
from config import Config
from extensions import mongo, jwt, limiter, mail

# Import blueprints
from routes.auth import auth_bp
from routes.accounts import accounts_bp
from routes.transactions import transactions_bp
from routes.users import users_bp

def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    mongo.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    
    # Configure CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(accounts_bp, url_prefix='/api/accounts')
    app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    
    # Root endpoint
    @app.route('/', methods=['GET'])
    def root():
        return jsonify({
            'message': 'Welcome to Bharat Bank API',
            'version': '1.0.0',
            'currency': 'INR',
            'endpoints': {
                'health': '/api/health',
                'auth': {
                    'register': 'POST /api/auth/register',
                    'login': 'POST /api/auth/login',
                    'logout': 'POST /api/auth/logout'
                },
                'users': {
                    'profile': 'GET /api/users/profile',
                    'update_profile': 'PUT /api/users/profile'
                },
                'accounts': {
                    'list': 'GET /api/accounts/',
                    'create': 'POST /api/accounts/',
                    'details': 'GET /api/accounts/{id}'
                },
                'transactions': {
                    'list': 'GET /api/transactions/',
                    'create': 'POST /api/transactions/',
                    'details': 'GET /api/transactions/{id}'
                }
            }
        })
    
    # Health check endpoint
    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'OK',
            'message': 'Bharat Bank API is running',
            'version': '1.0.0',
            'currency': 'INR'
        })
    
    # Global error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'message': 'Resource not found'
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500
    
    @app.errorhandler(429)
    def rate_limit_handler(error):
        return jsonify({
            'success': False,
            'message': 'Rate limit exceeded. Please try again later.'
        }), 429
    
    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'success': False,
            'message': 'Token has expired'
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            'success': False,
            'message': 'Invalid token'
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            'success': False,
            'message': 'Access denied. No token provided.'
        }), 401
    
    return app

# Create the app instance
app = create_app()

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=app.config['DEBUG']
    )
