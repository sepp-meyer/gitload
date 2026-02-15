# 1. Wähle ein Basis-Image (zum Beispiel Python 3.9 slim)
FROM python:3.9-slim

# 2. Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# 3. Kopiere zunächst die requirements.txt ins Container-Workdir
COPY requirements.txt /app/

# 4. Installiere Python-Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

# 5. Kopiere den Rest deines Projektcodes ins Container-Workdir
COPY . /app

# 6. Exponiere den gewünschten Port (5004)
EXPOSE 5004

# 7. Starte die Anwendung mit Gunicorn unter Nutzung der App-Factory.
#    Hier wird "app:create_app()" verwendet, damit Gunicorn die App über die Factory-Funktion erstellt.
CMD ["gunicorn", "--bind", "0.0.0.0:5004", "app:create_app()"]
