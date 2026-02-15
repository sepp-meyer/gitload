# app/__init__.py
from flask import Flask
from config import Config

def create_app():
    app = Flask(__name__, static_url_path='/gitload/static', static_folder='static')
    app.config.from_object(Config)
    
    from app.routes import bp
    app.register_blueprint(bp, url_prefix='/gitload')
    
    return app
