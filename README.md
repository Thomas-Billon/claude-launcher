# claude-launcher

Launcher interactif pour **Claude Code** : choix du **compte**, puis du **projet**, puis lancement de `claude` dans le dossier choisi.

- 🕘 Les **5 derniers dossiers** ouverts avec le compte en tête de liste
- 📁 Puis les **sous-dossiers** du dossier par défaut, les plus récemment lancés en premier
- 🔄 **Synchro git** du launcher et du repo de skills partagés au démarrage

> [!WARNING]
> **Code généré par IA** : ce repo a été écrit avec Claude Code. Il est fourni **tel quel, sans aucune garantie** : relire les scripts avant de les lancer, leur utilisation se fait **à vos risques et périls**.

## Prérequis

| Outil | Remarque |
|-------|----------|
| **Windows** | Lecture du clavier via `msvcrt` |
| **Python 3** | Dans le `PATH` |
| **Claude Code CLI** | `claude` dans le `PATH` |
| **git** | Identité et identifiants configurés par l'utilisateur, jamais par le launcher |

## Installation

```powershell
./install.ps1
```

1. Crée le raccourci **« Claude Code »** dans le menu Démarrer
2. Si `config.json` existe : affiche le repo de skills actuel et propose de le garder (fin du script)
3. Sinon, choix du **repo de skills partagés** (enregistré dans `config.json`) :
   - **Repo local existant** : saisie du chemin
   - **Nouveau repo** depuis le template [claude-skills-base](https://github.com/Thomas-Billon/claude-skills-base) : « Use this template » dans le navigateur, collage de l'URL, puis `git clone` en local
   - **Aucun**
4. Avec un repo : mise en place du [`CLAUDE.md` global](#claudemd-global)
5. Propose de lancer l'`install.ps1` du repo de skills (jonctions, relais `~/.claude/CLAUDE.md`, remote `upstream`)

> [!NOTE]
> - Toute action git est **affichée puis confirmée** (`Y/N`). Aucun accès GitHub requis, seulement git.
> - Repo déplacé ou nouvelle machine : **relancer le script** (chemins du raccourci déduits de l'emplacement du repo).
> - Le raccourci peut ensuite être **épinglé à la barre des tâches**.

### `CLAUDE.md` global

Avec un repo de skills, `~/.claude/CLAUDE.md` devient un **relais** qui importe le `CLAUDE.md` du repo. Un fichier vide compte comme absent.

| `~/.claude/CLAUDE.md` | `CLAUDE.md` du repo | Action |
|---|---|---|
| Absent | — | Aucune : l'`install.ps1` des skills crée le fichier du repo (vide) et le relais |
| Relais vers ce repo | — | Aucune |
| Relais vers un autre fichier | Présent, ou référencé vide | Propose de repointer le relais vers ce repo |
| Relais vers un autre fichier | Absent | Propose d'importer le fichier référencé (comme ci-dessous) |
| Présent | Absent | Propose d'importer son contenu dans le repo, puis de le remplacer par le relais (commit proposé au lancement suivant) |
| Présent | Présent | **Fusion manuelle** : reporter les règles, supprimer le fichier, relancer l'`install.ps1` des skills |

## Désinstallation

```powershell
./uninstall.ps1
```

- 🗑️ Supprime le raccourci et `config.json` (après confirmation)
- 👤 Pour chaque compte (`Y/N`) : `claude auth logout` puis suppression du dossier (jonctions retirées d'abord)
- 🛡️ **Jamais touchés** : `~/.claude` et les repos clonés

## Utilisation

Via le raccourci du menu Démarrer, ou en ligne de commande :

```powershell
python claude_launcher.py                  # dossier par défaut du compte, sinon dossier utilisateur
python claude_launcher.py -d <dossier>     # dossier racine ponctuel, prioritaire
```

### Choix du compte

| Touche | Action |
|--------|--------|
| `↑` `↓` | Sélectionner un compte |
| `Entrée` | Utiliser le compte (ou ajouter un compte sur `+ Add account`) |
| `→` | Ouvrir les [options du compte](#options-dun-compte) |
| `←` `Échap` | Fermer les options |
| `Échap` | Quitter (depuis la liste) |
| `Ctrl+C` | Quitter |

### Choix du dossier

Liste : les **5 dossiers récents** (`nom  (dossier parent)`), une ligne vide, puis les **sous-dossiers** du dossier courant.

| Touche | Action |
|--------|--------|
| `↑` `↓` | Sélectionner un dossier |
| `→` | Entrer dans le dossier |
| `←` | Remonter au dossier parent |
| `Entrée` | **Lancer Claude Code** |
| `Échap` | Revenir au choix du compte |
| `Ctrl+C` | Quitter |

## Comptes

Chaque compte a son dossier `~/.claude-accounts/<id>/`, passé à `claude` via `CLAUDE_CONFIG_DIR`.

- ⚡ Plusieurs comptes peuvent tourner **en parallèle**
- 🔑 **Une seule connexion** par compte : Claude Code rafraîchit lui-même ses jetons

> [!IMPORTANT]
> **Sécurité** : le launcher ne lit ni n'enregistre **aucun identifiant ni adresse mail**.
> - Connexion et déconnexion faites par Claude Code (`claude auth logout`)
> - Adresse affichée lue dans le profil tenu par Claude Code (`.claude.json`)
> - Statut connecté : seule la **présence** de `.credentials.json` est vérifiée, jamais son contenu
> - Dossiers des comptes **hors du repo**

### Options d'un compte

Nom et adresse mail (en gris) affichés pour chaque compte, triés par ordre alphabétique. Données dans `~/.claude-accounts/launcher_state.json`.

| Option | Effet |
|--------|-------|
| `+ Add account` | Demande un nom (`Perso`, `Work`…) et crée le dossier. Connexion au premier lancement |
| `Use account` | Passe au choix du dossier |
| `Rename account` | Modifie le nom |
| `Set default folder` | Choisit le dossier de départ du compte (`Entrée` enregistre, `Échap` annule) |
| `Remove from history` | Liste l'historique, du plus récent au plus ancien : `Entrée` retire le dossier |
| `Clear history` | Vide l'historique du compte (après confirmation) |
| `Delete account` | Déconnecte, retire les jonctions et supprime dossier, réglages et historique (après confirmation) |

- 🕘 **Historique** : date du dernier lancement de chaque dossier, par compte. Sert aux dossiers récents et au tri.
- ⚠️ **Doublon** : avertissement à la fermeture si un autre compte utilise la même adresse.
- 🏷️ Un compte sans nom (antérieur aux noms) affiche son adresse.

### Configuration partagée

`~/.claude` reste la **base commune** (alimentée par le repo de skills). Aucun compte ne s'y connecte.

| Élément | Partage |
|---------|---------|
| `skills/`, `plugins/` | Jonctions vers `~/.claude` |
| `CLAUDE.md` | Une ligne `@~/.claude/CLAUDE.md` |
| `settings.json` | `claude --settings ~/.claude/settings.json` à chaque lancement |

> [!TIP]
> `--settings` prime sur les réglages des projets et du compte : un réglage pour **tous les comptes** se met dans `~/.claude/settings.json`.

## Mises à jour au démarrage

Avant le menu, synchro du **repo du launcher** puis du **repo de skills** (une ligne chacun dans l'en-tête : `Launcher`, `Skills`). Après un `git fetch` silencieux, chaque action est **proposée** :

| # | Situation | Question | Commande |
|---|-----------|----------|----------|
| 1 | Changements non commités | `N changed files, commit & push?` | `git add --all` + commit (message modifiable) |
| 2 | Nouveaux commits distants | `N new commits, pull?` | `git pull --rebase=merges --autostash` |
| 3 | Commits locaux non poussés | `N local commits not pushed, push?` | `git push` |

- Étape **3** : sautée si des commits distants restent à récupérer ; question omise si un push a déjà été confirmé
- Conflit au pull : rebase **annulé**, synchro à faire à la main
- Échec (hors ligne, push refusé, conflit) : affiché **en jaune**, ne bloque **jamais** le lancement

**Saisie** : `Y/N` puis `Entrée` (question reposée sinon). Message de commit : `←` `→` `Début` `Fin` `Retour arrière` `Suppr`, `Entrée` valide, `Échap` renonce.

### Launcher

- **Pull uniquement** (étape 2) : les changements locaux du launcher se gèrent à la main
- Commits récupérés → **relance automatique** sur la nouvelle version
- Pas un repo git → étape ignorée, pas de ligne `Launcher`

### Skills (optionnel)

Configuré dans `config.json` (ex : repo issu de [claude-skills-base](https://github.com/Thomas-Billon/claude-skills-base)). Toutes les étapes, plus :

- 🔀 **Remote `upstream`** (la base) fetché aussi : `N new commits on your repo, M on the base repo, pull?`
- 🔀 Après le pull, **merge de la base** proposé : `M base commits to merge, merge, commit & push?` (message par défaut `Merged base repo updates`, conflit → merge annulé)
- ⚙️ Après un pull ou un merge : lancement de son `install.ps1` s'il existe

Sans repo : étape ignorée. Pour activer, changer ou désactiver : relancer `./install.ps1`.

## Code

| Fichier | Rôle |
|---------|------|
| `claude_launcher.py` | **Point d'entrée** : arguments, enchaînement des étapes, relance après mise à jour |
| `install.ps1` | Raccourci, repo de skills, `CLAUDE.md` global |
| `uninstall.ps1` | Suppression du raccourci, de la config et des comptes |
| `launcher/paths.py` | Chemins utilisés (repo, `config.json`, `~/.claude-accounts`, `~/.claude`) |
| `launcher/repo_sync.py` | Synchro des repos au démarrage |
| `launcher/git_repo.py` | Commandes git (fetch, pull, merge, commit, push) |
| `launcher/accounts.py` | Comptes : dossiers, jonctions, commande de lancement |
| `launcher/launcher_state.py` | `launcher_state.json` : nom, dossier par défaut, historique |
| `launcher/account_menu.py` | Menu des comptes, options et historique |
| `launcher/folder_menu.py` | Choix du dossier |
| `launcher/prompts.py` | Questions `Y/N`, messages de commit, noms de compte |
| `launcher/keyboard.py` | Lecture du clavier |
| `launcher/terminal_ui.py` | Rendu console : en-tête, listes, messages |

## Fichiers locaux

Non versionnés (`.gitignore`), propres à chaque machine :

| Fichier | Rôle |
|---------|------|
| `*.lnk` | Raccourcis générés par `install.ps1` |
| `config.json` | Chemin du repo de skills (`skills_repo`, `null` si désactivé) |
