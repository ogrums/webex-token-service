# webex-token-service

# Donner les droits d'exécution au script
sudo chmod +x /opt/webex-token-service/token_service.py

# Créer les fichiers de logs (avec les bons droits)
sudo touch /var/log/webex-token-service.log
sudo touch /var/log/webex-token-service-error.log
sudo chown www-data:www-data /var/log/webex-token-service*.log

# Copier le fichiers service
sudo cp /opt/webex-token-service/webex-token.service /usr/lib/systemd/system/webex-token.service

# Recharger systemd
sudo systemctl daemon-reload

# Démarrer le service
sudo systemctl start webex-token

# Activer le démarrage automatique au boot
sudo systemctl enable webex-token

# Vérifier le statut
sudo systemctl status webex-token

# Consulter les logs en temps réel
sudo journalctl -u webex-token -f

