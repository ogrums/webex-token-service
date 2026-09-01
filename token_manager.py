import json
import logging
import os
import tempfile
import time
from pathlib import Path

import requests

from config import TOKEN_FILE, TOKEN_URL, CLIENT_ID, CLIENT_SECRET


logger = logging.getLogger(__name__)

TOKEN_PATH = Path(TOKEN_FILE)
tokens = None


def load_tokens():
    """
    Charge les tokens depuis tokens.json.

    Retourne :
        True  : fichier valide et tokens chargés
        False : fichier absent, vide ou invalide
    """
    global tokens

    try:
        if not TOKEN_PATH.exists():
            logger.warning("Fichier de tokens absent : %s", TOKEN_PATH)
            tokens = None
            return False

        if TOKEN_PATH.stat().st_size == 0:
            logger.warning("Fichier de tokens vide : %s", TOKEN_PATH)
            tokens = None
            return False

        with TOKEN_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            logger.error(
                "Le fichier %s doit contenir un objet JSON.",
                TOKEN_PATH
            )
            tokens = None
            return False

        if not data.get("access_token") and not data.get("refresh_token"):
            logger.warning("Aucun token trouvé dans %s", TOKEN_PATH)
            tokens = None
            return False

        tokens = data
        logger.info("Tokens chargés depuis %s", TOKEN_PATH)
        return True

    except json.JSONDecodeError as error:
        logger.error(
            "JSON invalide dans %s - ligne %s, colonne %s",
            TOKEN_PATH,
            error.lineno,
            error.colno
        )
        tokens = None
        return False

    except PermissionError:
        logger.error("Permission refusée pour lire %s", TOKEN_PATH)
        tokens = None
        return False

    except OSError as error:
        logger.error(
            "Impossible de lire %s : %s",
            TOKEN_PATH,
            error
        )
        tokens = None
        return False


def save_tokens(new_tokens):
    """
    Sauvegarde les tokens de manière atomique.
    """
    global tokens

    if not isinstance(new_tokens, dict):
        raise ValueError("Les tokens doivent être un dictionnaire.")

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_path = tempfile.mkstemp(
        dir=TOKEN_PATH.parent,
        prefix=".tokens-",
        text=True
    )

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(new_tokens, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, TOKEN_PATH)

        tokens = new_tokens
        logger.info("Tokens sauvegardés dans %s", TOKEN_PATH)

    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass

        raise


def refresh_access_token():
    """
    Rafraîchit l'access token avec le refresh token.

    Retourne :
        str  : nouvel access token
        None : échec
    """
    global tokens

    if not tokens or not tokens.get("refresh_token"):
        logger.error("Aucun refresh_token disponible.")
        return None

    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"]
    }

    try:
        logger.info("Rafraîchissement du token d'accès...")

        response = requests.post(
            TOKEN_URL,
            data=data,
            timeout=30
        )

        response.raise_for_status()
        new_tokens = response.json()

        if not new_tokens.get("access_token"):
            logger.error(
                "La réponse Webex ne contient pas d'access_token."
            )
            return None

        # Le refresh_token peut ne pas être renvoyé à chaque fois
        if not new_tokens.get("refresh_token"):
            new_tokens["refresh_token"] = tokens["refresh_token"]

        new_tokens["expires_at"] = (
            time.time() + new_tokens.get("expires_in", 3600)
        )

        save_tokens(new_tokens)

        logger.info("Token rafraîchi avec succès.")
        return new_tokens["access_token"]

    except json.JSONDecodeError:
        logger.error("La réponse Webex n'est pas un JSON valide.")
        return None

    except requests.RequestException as error:
        logger.error(
            "Erreur réseau lors du rafraîchissement : %s",
            error
        )
        return None

    except OSError as error:
        logger.error(
            "Impossible de sauvegarder les tokens : %s",
            error
        )
        return None


def get_valid_access_token():
    """
    Retourne un access token valide.

    Si le fichier est absent, vide ou invalide, tente de charger les tokens.
    Si le token est expiré, tente de le rafraîchir.

    Retourne :
        str  : access token valide
        None : aucun token disponible
    """
    global tokens

    if not tokens:
        if not load_tokens():
            logger.warning("Aucun fichier de tokens utilisable.")
            return None

    expires_at = tokens.get("expires_at", 0)

    # Marge de sécurité de 60 secondes
    if time.time() >= expires_at - 60:
        logger.info("Access token absent ou expiré.")
        return refresh_access_token()

    access_token = tokens.get("access_token")

    if not access_token:
        logger.warning("Access token absent.")
        return refresh_access_token()

    return access_token