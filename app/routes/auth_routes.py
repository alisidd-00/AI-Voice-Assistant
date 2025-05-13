import os
from flask import Blueprint, request, jsonify, redirect, url_for, session
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from app.models import db, User
import json
import requests
from requests.structures import CaseInsensitiveDict
import secrets

auth_bp = Blueprint("auth", __name__)

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/api/auth/google/callback")
SCOPES = ['https://www.googleapis.com/auth/userinfo.email', 
          'https://www.googleapis.com/auth/userinfo.profile',
          'openid']

# Store state in memory (not secure for production, but works for demo)
# In production, use a proper session or cache mechanism
STATE_STORE = {}

@auth_bp.route("/google/login", methods=["GET"])
def google_login():
    """Generate Google OAuth URL and redirect user to Google's login page"""
    
    # Get optional frontend callback URL
    frontend_callback = request.args.get('callback')
    
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        },
        scopes=SCOPES
    )
    
    # Set the redirect URI
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    
    # Generate a random state
    state = secrets.token_urlsafe(16)
    
    # Generate URL for request to Google's OAuth 2.0 server
    authorization_url, _ = flow.authorization_url(
        access_type='offline',  # Enable refresh tokens
        include_granted_scopes='true',
        prompt='consent',  # Force to always get refresh token
        state=state
    )
    
    # Store state for verification and the frontend callback if provided
    STATE_STORE[state] = {'verified': True, 'frontend_callback': frontend_callback}
    
    # Redirect user to Google's authorization page
    return redirect(authorization_url)

@auth_bp.route("/google/callback", methods=["GET"])
def google_callback():
    """Handle Google OAuth callback and create/update user"""
    
    # Verify state matches to prevent CSRF attacks
    state = request.args.get('state')
    if not state or state not in STATE_STORE:
        return jsonify({"error": "State verification failed"}), 401
    
    # Get the frontend callback if it exists
    stored_state = STATE_STORE.pop(state, None)
    frontend_callback = stored_state.get('frontend_callback')
    
    # Create flow instance with same configuration as the login route
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        state=state
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    
    # Use the authorization code to fetch tokens
    flow.fetch_token(authorization_response=request.url)
    
    # Get credentials from flow
    credentials = flow.credentials
    
    # Fetch user information from Google
    user_info = get_user_info(credentials)
    
    # Check if user exists by Google ID
    user = User.query.filter_by(google_id=user_info['id']).first()
    
    # If not, check by email
    if not user and 'email' in user_info:
        user = User.query.filter_by(email=user_info['email']).first()
    
    # If user doesn't exist, create a new one
    if not user:
        user = User(
            google_id=user_info['id'],
            email=user_info.get('email'),
            name=user_info.get('name'),
            google_token=credentials.token,
            google_refresh_token=credentials.refresh_token
        )
        db.session.add(user)
    else:
        # Update existing user with Google info
        user.google_id = user_info['id']
        user.name = user_info.get('name', user.name)
        user.email = user_info.get('email', user.email)
        user.google_token = credentials.token
        user.google_refresh_token = credentials.refresh_token or user.google_refresh_token
    
    db.session.commit()
    
    # Create user_data for response/redirect
    user_data = {
        "id": user.id,
        "name": user.name,
        "email": user.email
    }
    
    # If frontend callback URL is provided, redirect there
    if frontend_callback:
        # In production, you would set a secure cookie or JWT instead of using URL params
        return redirect(f"{frontend_callback}?login=success")
    
    # Otherwise return JSON
    return jsonify({
        "message": "Successfully authenticated with Google",
        "user": user_data
    })

def get_user_info(credentials):
    """Fetch user information from Google using credentials"""
    
    # Build Google API service
    service = build('oauth2', 'v2', credentials=credentials)
    
    # Call the userinfo API
    user_info = service.userinfo().get().execute()
    
    return user_info

@auth_bp.route("/user", methods=["GET"])
def get_current_user():
    """Get the current user based on the provided auth token"""
    # This endpoint would normally validate a JWT or session cookie
    # For demo purposes, we're mocking this with URL params
    
    # Check if user is authenticated (in production you'd check session/JWT)
    user_id = request.args.get('user_id')
    
    if not user_id:
        return jsonify({"authenticated": False}), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"authenticated": False}), 401
    
    return jsonify({
        "authenticated": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email
        }
    })

@auth_bp.route("/revoke", methods=["POST"])
def revoke_token():
    """Revoke Google OAuth token"""
    user_id = request.json.get('user_id')
    
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    
    user = User.query.get(user_id)
    if not user or not user.google_token:
        return jsonify({"error": "User not found or no token available"}), 404
    
    # Revoke the token
    url = f"https://oauth2.googleapis.com/revoke?token={user.google_token}"
    headers = CaseInsensitiveDict()
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 200:
        # Clear tokens from user record
        user.google_token = None
        user.google_refresh_token = None
        db.session.commit()
        return jsonify({"message": "Token revoked successfully"})
    else:
        return jsonify({"error": "Failed to revoke token", "details": response.text}), 400

@auth_bp.route("/user/me", methods=["GET"])
def get_current_user_me():
    """Get the current authenticated user based on session or token"""
    
    # In a production app, this would check for an auth token or session cookie
    # For demo purposes, we'll create a mock user with the Google profile info
    
    # Check if user is in session (for demonstration)
    # In a real app, you'd use a proper auth mechanism with JWTs or session management
    
    try:
        # Get the Google user information from the request's auth header or cookie
        # For demonstration purposes, we'll return a mock user 
        # In production, this would extract a real token and validate it
        
        # Get a sample user from the database if it exists
        user = User.query.first()
        
        if user:
            return jsonify({
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email
                }
            })
        else:
            # Mock user if none exists in the database
            return jsonify({
                "user": {
                    "id": 1,
                    "name": "Demo User",
                    "email": "demo@example.com"
                }
            })
    except Exception as e:
        print(f"Error fetching user: {e}")
        return jsonify({"error": "Failed to get current user"}), 401 