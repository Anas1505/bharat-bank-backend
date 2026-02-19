#!/usr/bin/env python3
"""Startup script for the Mobile Banking API server."""

import os
from app import create_app

def main():
    """Main function to start the Flask server."""
    print("Starting Mobile Banking API Server...")
    print("=" * 50)
    
    # Create the Flask app
    app = create_app()
    
    # Get configuration from environment or use defaults
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"Server Configuration:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Debug: {debug}")
    print(f"  Environment: {os.environ.get('FLASK_ENV', 'production')}")
    print("=" * 50)
    print("Available endpoints:")
    print("  GET  /api/health           - Health check")
    print("  POST /api/auth/register    - User registration")
    print("  POST /api/auth/login       - User login")
    print("  GET  /api/users/profile    - User profile")
    print("  GET  /api/accounts/        - User accounts")
    print("  GET  /api/transactions/    - Transaction history")
    print("=" * 50)
    
    if not debug:
        print("Note: Running in production mode. Set FLASK_ENV=development for debug mode.")
    
    print(f"Starting server at http://{host}:{port}")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        app.run(
            host=host,
            port=port,
            debug=debug,
            use_reloader=debug
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
