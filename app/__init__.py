from flask import Flask
from app.extensions import db  # <== from extensions now
import os

def create_app():
    here = os.path.abspath(os.path.dirname(__file__))

    app = Flask(
        __name__,
        static_folder=os.path.join(here, "..", "static"),
        static_url_path="/static"
    )
    app.config.from_pyfile("config.py")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")

    db.init_app(app)

    from .routes.assistant_routes import assistant_bp
    from .routes.voice_routes import voice_bp
    from .routes.auth_routes import auth_bp
    from .routes.tts_routes import tts_bp
    from .routes.rag_routes import rag_bp


    app.register_blueprint(assistant_bp, url_prefix="/api")
    app.register_blueprint(voice_bp, url_prefix="/voice")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(tts_bp)
    app.register_blueprint(rag_bp) 

    with app.app_context():
        db.create_all()

    return app
