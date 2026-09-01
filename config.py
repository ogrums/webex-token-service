# config.py
CLIENT_ID = "VOTRE_CLIENT_ID"
CLIENT_SECRET = "VOTRE_CLIENT_SECRET"
REDIRECT_URI = "http://localhost:5000/oauth/callback"
AUTH_URL = "https://webexapis.com/v1/authorize"
TOKEN_URL = "https://webexapis.com/v1/access_token"

# URL de l'API Webex CCX (adaptez selon votre région)
WXCC_API_URL = "https://api.wxcc-eu1.cisco.com"
SEARCH_ENDPOINT = "/search"

# Fichier de stockage des tokens (chemin absolu)
TOKEN_FILE = "/opt/webex-token-service/tokens.json"

# Paramètres du serveur Flask
HOST = "0.0.0.0"
PORT = 5000