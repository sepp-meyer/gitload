# app/__init__.py
from flask import Flask
from config import Config

# Erstelle die Flask-App und lade die Konfiguration
app = Flask(__name__)
app.config.from_object(Config)

# Importiere die Routen (wichtig: dies muss nach der App-Erstellung erfolgen)
from app import routes
