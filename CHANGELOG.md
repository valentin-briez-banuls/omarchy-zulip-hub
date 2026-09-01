# Historique des versions

## 2.0.0 — 2026-09-01

- Distribution native via Omarchy Plugin Marketplace avec manifeste racine namespacé.
- Bridge Python supervisé par le service Quickshell du plugin, sans installation systemd.
- Raccourcis Hyprland facultatifs, installables et retirables depuis les réglages.
- Documentation publique bilingue et procédure de retrait conservatrice.

## 1.2.0 — 2026-09-01

- `Super+Z` ouvre directement Zulip Hub ; `Super+Maj+Z` conserve le workspace dédié.
- Interface intégralement pilotable au clavier avec un curseur visible dans toutes les vues.
- Accueil simplifié à « Nouveau MP » et « Réglages » ; les actions avancées sont regroupées dans les réglages.
- Nouveau logo Zulip monochrome vectoriel accordé au thème Omarchy.
- Interface française ou anglaise selon la locale système.
- Redémarrage sûr d’Omarchy Shell après installation ou mise à jour, avec contrôle de la version réellement chargée.

## 1.1.0 — 2026-09-01

- Composeur graphique de messages directs individuels et collectifs.
- Annuaire Zulip recherchable avec contacts récents prioritaires.
- Brouillon conservé uniquement en mémoire et envoi sécurisé par stdin.
- Limite de message fournie par le serveur et protection contre les renvois ambigus.

## 1.0.0 — 2026-09-01

- Mise à jour transactionnelle avec migration versionnée et rollback complet.
- Préservation de l'état actif et activé du service systemd utilisateur.
- Porte de sortie automatisée couvrant Python, QML, Hyprland et le manifeste.
- Licence MIT et documentation utilisateur finale.

## 0.7.0

- Réglages graphiques des notifications, canaux et commandes d'ouverture.
- Diagnostic du bridge et reconnexion persistante.
- Correction de l'encodage JSON des booléens pour l'API Zulip.

## 0.6.0

- Assistant graphique sécurisé pour connecter le compte sans terminal.
- Clé API transmise par stdin et stockée dans Secret Service.

## 0.5.0

- Installation, sauvegarde, activation et désinstallation gérées.

## 0.4.0

- Workspace spécial Hyprland et raccourci `Super+Z`.

## 0.3.0

- Notifications natives sécurisées et liens profonds Zulip.

## 0.2.0

- Widget Omarchy Shell, compteurs et conversations récentes.

## 0.1.0

- Bridge événementiel Zulip, état local atomique et stockage du secret.
