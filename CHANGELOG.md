# Historique des versions

## 2.1.2 — 2026-09-02

- Plus aucun nouvel essai immédiat. Une file d'événements rejetée relançait
  l'enregistrement sans la moindre temporisation, seul chemin d'erreur du
  bridge à ne pas appliquer de report exponentiel. Répété, il consommait le
  quota d'API du compte — le même que celui du client Zulip, qui se retrouvait
  alors bloqué en `RATE_LIMIT_HIT`.
- Le délai réclamé par le serveur est désormais lu dans la réponse et
  respecté, y compris au-delà du report maximal, plutôt qu'ignoré.

## 2.1.1 — 2026-09-02

- Un seul bridge à la fois. Le shell peut tenir deux instances du service du
  plugin en vie simultanément — observé après `omarchy plugin update`, qui
  charge la nouvelle avant de détruire l'ancienne. Les deux ouvraient alors
  chacune une file d'événements Zulip et les notifications arrivaient en
  double. Un verrou exclusif fait patienter le second bridge, qui prend le
  relais de lui-même si le premier s'arrête.

## 2.1.0 — 2026-09-02

- Réponse depuis le panneau : `A` ou le bouton ↩ répond dans la conversation
  d'origine, aussi bien pour un message direct que pour un canal.
- La destination d'une réponse est déduite par le bridge depuis son état local ;
  l'interface ne transmet qu'un identifiant de message, jamais un destinataire.
- Envoi dans un canal et son topic, avec repli sur les serveurs Zulip
  antérieurs à la 2.0.

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
