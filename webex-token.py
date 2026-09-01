#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import logging
import requests
from flask import Flask, request, jsonify
import threading
import time
import json
import webbrowser
from urllib.parse import urlencode

# Importer la configuration
from config import *

# Configuration du logging
LOG_FILE = "/var/log/webex-token-service.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

tokens = None

def load_tokens():
    global tokens
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        logger.info("Tokens chargés depuis %s", TOKEN_FILE)
        return True
    except FileNotFoundError:
        logger.warning("Fichier tokens.json non trouvé.")
        return False

def save_tokens(t):
    global tokens
    tokens = t
    with open(TOKEN_FILE, 'w') as f:
        json.dump(t, f)
    logger.info("Tokens sauvegardés dans %s", TOKEN_FILE)

def refresh_access_token():
    global tokens
    if not tokens or 'refresh_token' not in tokens:
        logger.error("Aucun refresh_token disponible pour le rafraîchissement.")
        return None

    logger.info("Rafraîchissement du token d'accès...")
    data = {
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': tokens['refresh_token']
    }
    try:
        response = requests.post(TOKEN_URL, data=data)
        response.raise_for_status()
        new_tokens = response.json()
        if 'refresh_token' not in new_tokens:
            new_tokens['refresh_token'] = tokens['refresh_token']
        # Ajouter un timestamp d'expiration (durée de vie typique: 3600s)
        new_tokens['expires_at'] = time.time() + new_tokens.get('expires_in', 3600)
        save_tokens(new_tokens)
        logger.info("Token rafraîchi avec succès.")
        return new_tokens['access_token']
    except Exception as e:
        logger.error("Erreur lors du rafraîchissement : %s", e)
        return None

@app.route('/')
def index():
    auth_params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': 'cjp:config cjp:config_read contact-center:queues_read',
        'state': 'random_state_string'
    }
    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"
    return f'<a href="{auth_url}" target="_blank">1. Autoriser l\'application Webex</a>'

@app.route('/oauth/callback')
def oauth_callback():
    auth_code = request.args.get('code')
    if not auth_code:
        return "Erreur : Code d'autorisation manquant."

    logger.info("Code d'autorisation reçu.")
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI
    }
    try:
        response = requests.post(TOKEN_URL, data=data)
        response.raise_for_status()
        token_data = response.json()
        token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)
        save_tokens(token_data)
        logger.info("Authentification réussie. Tokens stockés.")
        return "Authentification réussie ! Vous pouvez fermer cette page."
    except Exception as e:
        logger.error("Erreur lors de l'échange du code : %s", e)
        return f"Erreur : {e}"

@app.route('/token')
def get_token():
    global tokens
    if not tokens:
        if not load_tokens():
            return jsonify({"error": "Tokens non trouvés. Authentifiez-vous via /"}), 400

    # Vérifier l'expiration (marge 60s)
    if time.time() > tokens.get('expires_at', 0) - 60:
        new_token = refresh_access_token()
        if not new_token:
            return jsonify({"error": "Impossible de rafraîchir le token."}), 400
        return jsonify({"access_token": new_token})
    else:
        return jsonify({"access_token": tokens['access_token']})

@app.route('/graphql', methods=['POST'])
def graphql_query():
    # Récupérer le payload GraphQL
    graphql_payload = request.get_json()
    if not graphql_payload or 'query' not in graphql_payload:
        return jsonify({"error": "Requête GraphQL invalide"}), 400

    # Obtenir un token valide
    token_resp = get_token()
    if token_resp.status_code != 200:
        return token_resp
    access_token = token_resp.get_json().get('access_token')
    if not access_token:
        return jsonify({"error": "Token d'accès manquant"}), 500

    # Construire l'URL de l'API Webex
    org_id = request.args.get('orgId')
    url = f"{WXCC_API_URL}{SEARCH_ENDPOINT}"
    if org_id:
        url += f"?orgId={org_id}"

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    try:
        resp = requests.post(url, headers=headers, json=graphql_payload)
        resp.raise_for_status()
        return jsonify(resp.json())
    except requests.exceptions.RequestException as e:
        logger.error("Erreur appel API Webex : %s", e)
        return jsonify({"error": f"Erreur API : {e}"}), 500

def refresh_loop():
    """Boucle de rafraîchissement préventif."""
    while True:
        time.sleep(1800)  # toutes les 30 min
        if tokens and 'expires_at' in tokens:
            if time.time() > tokens['expires_at'] - 300:
                logger.info("Rafraîchissement préventif déclenché.")
                refresh_access_token()

if __name__ == '__main__':
    load_tokens()
    # Démarrer le thread de rafraîchissement
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    # Ouvrir la page d'authentification si pas de token
    if not tokens:
        webbrowser.open('http://localhost:5000/')
        logger.info("Aucun token trouvé. Ouvrez la page d'authentification.")

    logger.info("Service démarré sur %s:%s", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)