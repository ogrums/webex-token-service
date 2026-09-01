#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import requests
import threading
import time
import webbrowser

from flask import Flask, request, jsonify
from urllib.parse import urlencode

from config import *
import token_manager


LOG_FILE = "/var/log/webex-token-service.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    auth_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": (
            "cjp:config "
            "cjp:config_read "
            "contact-center:queues_read"
        ),
        "state": "random_state_string"
    }

    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"

    return (
        f'<a href="{auth_url}" target="_blank">'
        "1. Autoriser l'application Webex"
        "</a>"
    )


@app.route("/oauth/callback")
def oauth_callback():
    auth_code = request.args.get("code")

    if not auth_code:
        return "Erreur : code d'autorisation manquant.", 400

    logger.info("Code d'autorisation reçu.")

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "redirect_uri": REDIRECT_URI
    }

    try:
        response = requests.post(
            TOKEN_URL,
            data=data,
            timeout=30
        )

        response.raise_for_status()

        token_data = response.json()
        token_data["expires_at"] = (
            time.time() + token_data.get("expires_in", 3600)
        )

        token_manager.save_tokens(token_data)

        logger.info("Authentification réussie.")
        return "Authentification réussie ! Vous pouvez fermer cette page."

    except requests.RequestException as error:
        logger.error(
            "Erreur lors de l'échange du code : %s",
            error
        )
        return jsonify({
            "error": "Erreur lors de la communication avec Webex"
        }), 502

    except ValueError as error:
        logger.error(
            "Réponse JSON invalide de Webex : %s",
            error
        )
        return jsonify({
            "error": "Réponse invalide reçue de Webex"
        }), 502

    except OSError as error:
        logger.error(
            "Impossible de sauvegarder les tokens : %s",
            error
        )
        return jsonify({
            "error": "Impossible de sauvegarder les tokens"
        }), 500


@app.route("/token")
def get_token():
    access_token = token_manager.get_valid_access_token()

    if not access_token:
        return jsonify({
            "error": (
                "Token indisponible. "
                "Authentifiez-vous via la page d'accueil."
            )
        }), 401

    return jsonify({
        "access_token": access_token
    })


@app.route("/graphql", methods=["POST"])
def graphql_query():
    graphql_payload = request.get_json(silent=True)

    if not graphql_payload or "query" not in graphql_payload:
        return jsonify({
            "error": "Requête GraphQL invalide"
        }), 400

    # On récupère directement une chaîne ou None,
    # et non une réponse Flask.
    access_token = token_manager.get_valid_access_token()

    if not access_token:
        return jsonify({
            "error": (
                "Token indisponible. "
                "Authentifiez-vous via la page d'accueil."
            )
        }), 401

    org_id = request.args.get("orgId")

    url = f"{WXCC_API_URL}{SEARCH_ENDPOINT}"

    if org_id:
        url += f"?orgId={org_id}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=graphql_payload,
            timeout=30
        )

        response.raise_for_status()

        return jsonify(response.json())

    except requests.RequestException as error:
        logger.error(
            "Erreur lors de l'appel à l'API Webex : %s",
            error
        )
        return jsonify({
            "error": "Erreur lors de l'appel à l'API Webex"
        }), 502

    except ValueError:
        logger.error("La réponse Webex n'est pas un JSON valide.")
        return jsonify({
            "error": "Réponse JSON invalide de Webex"
        }), 502


def refresh_loop():
    """
    Rafraîchissement préventif toutes les 30 minutes.
    """
    while True:
        time.sleep(1800)

        if token_manager.tokens:
            expires_at = token_manager.tokens.get("expires_at", 0)

            if time.time() >= expires_at - 300:
                logger.info(
                    "Rafraîchissement préventif déclenché."
                )
                token_manager.refresh_access_token()


if __name__ == "__main__":
    token_manager.load_tokens()

    refresh_thread = threading.Thread(
        target=refresh_loop,
        daemon=True
    )
    refresh_thread.start()

    if not token_manager.tokens:
        logger.info(
            "Aucun token trouvé. "
            "Ouvrez http://localhost:5000/"
        )

        try:
            webbrowser.open("http://localhost:5000/")
        except Exception:
            pass

    logger.info(
        "Service démarré sur %s:%s",
        HOST,
        PORT
    )

    app.run(
        host=HOST,
        port=PORT,
        debug=False
    )