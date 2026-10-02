# claude-launcher

Launcher interactif qui lance Claude Code avec le compte choisi, dans le projet choisi.

Le launcher fait choisir un compte Claude, liste ensuite les 5 derniers dossiers ouverts avec ce compte, puis les sous-dossiers de son dossier par défaut (les plus récemment lancés en tête), et exécute `claude` dans le dossier sélectionné.

## Prérequis

- Windows (le launcher lit le clavier via `msvcrt`)
- Python 3 dans le `PATH`
- Claude Code CLI (`claude`) dans le `PATH`

## Installation

```powershell
./install.ps1
```

Le script :

1. crée le raccourci « Claude Code » dans le menu Démarrer ;
2. demande si un repo de skills partagés doit être utilisé (`Y/N`), puis son chemin local (voir [Mise à jour des skills](#mise-à-jour-des-skills-optionnel)). Le choix est enregistré dans `config.json`. Si ce fichier existe déjà, le script affiche le réglage actuel et propose de le garder.

Les chemins du raccourci sont déduits de l'emplacement du repo : relancer le script après un déplacement du repo ou sur une nouvelle machine. Le raccourci peut ensuite être épinglé à la barre des tâches.

## Utilisation

Via le raccourci du menu Démarrer, ou en ligne de commande :

```powershell
python claude_launcher.py                  # dossier par défaut du compte, sinon dossier utilisateur
python claude_launcher.py -d <dossier>     # dossier racine ponctuel, prioritaire
```

### Choix du compte

| Touche | Action |
|--------|--------|
| ↑ / ↓ | Sélectionner un compte |
| Entrée | Utiliser le compte (connexion dans le navigateur s'il est déconnecté) ; sur `+ Add account`, ajouter un compte |
| → | Ouvrir les options du compte : `Use account` / `Set default folder` / `Remove from history` / `Clear history` / `Delete account` |
| ← / Échap | Fermer les options (ou revenir aux options depuis l'historique) |
| Échap | Quitter (depuis la liste des comptes) |
| Ctrl+C | Quitter |

### Choix du dossier

En haut de la liste, séparés par une ligne vide, les 5 derniers dossiers ouverts avec ce compte, sous la forme `nom  (dossier parent)`. Viennent ensuite les sous-dossiers du dossier courant.

| Touche | Action |
|--------|--------|
| ↑ / ↓ | Sélectionner un dossier |
| → | Entrer dans le dossier sélectionné |
| ← | Remonter au dossier parent |
| Entrée | Lancer Claude Code dans le dossier sélectionné |
| Échap | Revenir au choix du compte |
| Ctrl+C | Quitter |

## Comptes

Chaque compte a son propre dossier de configuration Claude Code, `~/.claude-accounts/<id>/`, transmis à `claude` via la variable `CLAUDE_CONFIG_DIR`. Plusieurs comptes peuvent donc tourner en parallèle, et chacun garde sa connexion : Claude Code rafraîchit lui-même ses jetons, une seule connexion par compte suffit.

- **Sécurité** : le launcher ne lit ni n'enregistre aucun identifiant. Connexion, statut et déconnexion passent par `claude auth login` / `status` / `logout`. Le launcher ne stocke aucune adresse mail : les libellés sont lus dans le profil que Claude Code tient lui-même dans le dossier du compte (`.claude.json`). Pour savoir si le compte est connecté, seule la présence de `.credentials.json` est vérifiée, jamais son contenu. Avant de demander une reconnexion, le statut est confirmé par `claude auth status`. Les dossiers des comptes sont hors du repo.
- **Liste** : triée par ordre alphabétique.
- **Ajout** : `+ Add account` crée le dossier puis lance la connexion. Le dossier est supprimé si la connexion échoue ou si le compte est déjà dans la liste.
- **Dossier par défaut** : `Set default folder` ouvre une sélection de dossier, partant du dossier par défaut actuel du compte ou à défaut du dossier utilisateur. Entrée enregistre le dossier sélectionné (`~/.claude-accounts/launcher_state.json`), Échap annule. La sélection du dossier de lancement part ensuite de ce dossier pour ce compte.
- **Historique** : la date du dernier lancement de chaque dossier est enregistrée par compte, dans `~/.claude-accounts/launcher_state.json`. Elle sert à lister les dossiers récents et à trier les sous-dossiers. `Remove from history` liste tout l'historique du compte, du plus récent au plus ancien : Entrée retire le dossier sélectionné. `Clear history` vide tout l'historique du compte, après confirmation.
- **Suppression** : `Delete account` demande confirmation, déconnecte le compte puis supprime son dossier, son dossier par défaut et son historique (ses jonctions sont retirées d'abord, `~/.claude` n'est jamais touché).

### Configuration partagée

`~/.claude` reste la base commune (alimentée par exemple par le repo de skills partagés). Aucun compte ne s'y connecte. Le dossier de chaque compte y fait référence :

| Élément | Partage |
|---------|---------|
| `skills/`, `plugins/` | Jonctions vers `~/.claude` |
| `CLAUDE.md` | Une seule ligne `@~/.claude/CLAUDE.md`, qui importe le `CLAUDE.md` global |
| `settings.json` | Passé à chaque lancement via `claude --settings ~/.claude/settings.json` |

Les réglages passés par `--settings` priment sur ceux des projets et du compte : pour qu'un réglage s'applique à tous les comptes, le modifier dans `~/.claude/settings.json`.

## Mise à jour des skills (optionnel)

Si un repo de skills partagés est renseigné dans `config.json` (par exemple [claude-skills](https://github.com/Thomas-Billon/claude-skills)), le launcher le met à jour au démarrage, avant d'afficher le menu, pour que Claude Code démarre avec les derniers skills et le dernier `CLAUDE.md` global :

1. `git fetch` du repo
2. S'il est en retard sur sa branche distante : `git pull --ff-only`, puis son `install.ps1` s'il en a un

Le résultat s'affiche sur la ligne `Skills` des menus. Un échec (hors ligne, pull refusé, repo introuvable) n'empêche pas le lancement. Sans repo configuré, l'étape est ignorée et la ligne `Skills` n'apparaît pas.

Pour activer, changer ou désactiver le repo : relancer `./install.ps1`.

## Fichiers locaux

Non versionnés (`.gitignore`), propres à chaque machine :

| Fichier | Rôle |
|---------|------|
| `*.lnk` | Raccourcis générés par `install.ps1` |
| `config.json` | Chemin local du repo de skills partagés (`skills_repo`, `null` si désactivé), écrit par `install.ps1` |
