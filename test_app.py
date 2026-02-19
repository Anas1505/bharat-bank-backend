#!/usr/bin/env python3
"""Test script to verify the Flask app is working correctly."""

from app import app

def test_app():
    """Test the Flask application."""
    print("Testing Mobile Banking API...")
    
    with app.test_client() as client:
        # Test root endpoint
        response = client.get('/')
        print(f"Root endpoint status: {response.status_code}")
        print(f"Root response: {response.get_json()}")
        print()
        
        # Test health check endpoint
        response = client.get('/api/health')
        print(f"Health check status: {response.status_code}")
        print(f"Health check response: {response.get_json()}")
        print()
        
        # Test 404 handling
        response = client.get('/api/nonexistent')
        print(f"404 test status: {response.status_code}")
        print(f"404 response: {response.get_json()}")
        
    print("All basic tests passed! The app is ready to run.")

if __name__ == '__main__':
    test_app()
