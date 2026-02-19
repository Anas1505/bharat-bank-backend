from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail

# Initialize extensions
mongo = PyMongo()
jwt = JWTManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)
mail = Mail()

# JWT blacklist (in production, use Redis or database)
blacklisted_tokens = set()

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    """Check if a JWT token has been revoked"""
    return jwt_payload['jti'] in blacklisted_tokens

def revoke_token(jti):
    """Add token to blacklist"""
    blacklisted_tokens.add(jti)
