from app import create_app
import os

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allow OAuth over HTTP for development

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)