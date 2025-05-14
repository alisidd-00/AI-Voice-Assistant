# app/routes/auth_routes.py

from flask import Blueprint, request, redirect, session, jsonify
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from app.models import db, User
import os, secrets, requests

auth_bp = Blueprint("auth", __name__)

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5000/api/auth/google/callback")
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

@auth_bp.route("/google/login")
def google_login():
    frontend_cb = request.args.get("callback")
    if frontend_cb:
        session["frontend_callback"] = frontend_cb

    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri":    "https://accounts.google.com/o/oauth2/auth",
                "token_uri":   "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI

    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return redirect(auth_url)


@auth_bp.route("/google/callback")
def google_callback():
    # 1) Validate state
    state = request.args.get("state")
    if not state or state != session.get("oauth_state"):
        return jsonify({"error": "Invalid OAuth state"}), 401
    session.pop("oauth_state", None)

    # 2) Exchange code for tokens
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri":    "https://accounts.google.com/o/oauth2/auth",
                "token_uri":   "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        state=state,
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # 3) Fetch user info
    service   = build("oauth2", "v2", credentials=creds)
    profile   = service.userinfo().get().execute()
    google_id = profile["id"]
    email     = profile.get("email")
    name      = profile.get("name")

    # 4) Upsert User in DB
    user = User.query.filter_by(google_id=google_id).first() \
           or (email and User.query.filter_by(email=email).first())
    if not user:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            google_token=creds.token,
            google_refresh_token=creds.refresh_token,
        )
        db.session.add(user)
    else:
        user.google_token         = creds.token
        user.google_refresh_token = creds.refresh_token or user.google_refresh_token
        user.name                 = name or user.name
        user.email                = email or user.email

    db.session.commit()

    # 5) Remember “who” in the Flask session
    session["user_id"] = user.id

    payload = {"id": user.id, "name": user.name, "email": user.email}

    # 6) Redirect to front-end callback if given
    cb = session.pop("frontend_callback", None)
    if cb:
        sep = "&" if "?" in cb else "?"
        return redirect(f"{cb}{sep}login=success")

    # 7) Otherwise just return JSON
    return jsonify({"message": "Successfully authenticated", "user": payload})


@auth_bp.route("/user/me")
def get_current_user():
    """
    Returns the currently-authenticated user, based on the Flask session.
    Your front-end can call this right after the OAuth redirect to grab
    the user’s ID/name/email and store it in localStorage.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "user": {
            "id":    user.id,
            "name":  user.name,
            "email": user.email
        }
    })
