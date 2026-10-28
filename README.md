# claude-launcher

Launcher interactif pour **Claude Code** : choix du **compte**, puis du **projet**, puis lancement de `claude` dans le dossier choisi.

- ⭐ Les **dossiers favoris** du compte en tête de liste (`Ctrl+F` pour en ajouter ou en retirer)
- 📁 Puis les **sous-dossiers** du dossier par défaut, par ordre alphabétique, filtrables en tapant
- 💬 Nouvelle conversation, **reprise de la dernière** ou d'une conversation au choix
- 🌳 **Worktrees git** : plusieurs sessions sur un même repo, chacune sur sa branche `temp/`, sans toucher au dossier principal
- 🪟 Titre de fenêtre `Claude Code · <compte> · <projet>`
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

1. Signale en jaune les prérequis absents du `PATH` (`python`, `git`, `claude`), sans bloquer
2. Avec Windows Terminal : ajoute le profil **« Claude Code »** (fragment `%LOCALAPPDATA%\Microsoft\Windows Terminal\Fragments\claude-launcher`), à recharger en redémarrant Windows Terminal s'il est ouvert
3. Crée le raccourci **« Claude Code »** dans le menu Démarrer (remplace l'existant). Avec Windows Terminal, choix de son ouverture : **nouvel onglet** du profil dans la fenêtre [dédiée au launcher](#windows-terminal) ou **nouvelle fenêtre**. Sinon, fenêtre PowerShell
4. Si `config.json` existe : affiche le repo de skills actuel et propose de le garder (fin du script)
5. Sinon, choix du **repo de skills partagés** (enregistré dans `config.json`) :
   - **Repo local existant** : saisie du chemin (vide : retour au choix)
   - **Nouveau repo** depuis le template [claude-skills-base](https://github.com/Thomas-Billon/claude-skills-base) : « Use this template » dans le navigateur, collage de l'URL, puis `git clone` en local
   - **Aucun**
6. Avec un repo : mise en place du [`CLAUDE.md` global](#claudemd-global)
7. Propose de lancer l'`install.ps1` du repo de skills (jonctions, relais `~/.claude/CLAUDE.md`, remote `upstream`)

> [!NOTE]
> - Toute action git est **affichée puis confirmée** (`Y/N`). Aucun accès GitHub requis, seulement git.
> - Repo déplacé ou nouvelle machine : **relancer le script** (chemins du raccourci déduits de l'emplacement du repo).
> - Le raccourci peut ensuite être **épinglé à la barre des tâches**, ou recevoir une **touche globale** (Propriétés → Touche de raccourci, `Ctrl+Alt+<touche>`), conservée quand le script est relancé.
> - L'épingle de la barre des tâches **ne suit pas** les changements du raccourci : après une réinstallation qui le modifie (ex. passage à Windows Terminal), la désépingler puis épingler à nouveau le raccourci du menu Démarrer.

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

- 🗑️ Supprime le raccourci, le profil Windows Terminal et `config.json` (après confirmation)
- 👤 Pour chaque compte (`Y/N`) : `claude auth logout` puis suppression du dossier (jonctions retirées d'abord)
- 🛡️ **Jamais touchés** : `~/.claude`, `~/.claude-worktrees` (peut contenir du travail non fusionné) et les repos clonés

## Utilisation

Via le raccourci du menu Démarrer, ou en ligne de commande :

```powershell
python claude_launcher.py                              # dossier par défaut du compte, sinon dossier utilisateur
python claude_launcher.py -d <dossier>                 # dossier racine ponctuel, prioritaire
python claude_launcher.py -a <compte>                  # saute le choix du compte
python claude_launcher.py -a <compte> -d <dossier>     # lance Claude Code directement, sans menu
python claude_launcher.py -a Perso -- --model opus     # arguments après -- passés à claude
```

- `-a` : nom, adresse ou id du compte, sans tenir compte de la casse. `Échap` dans le choix du dossier revient quand même au choix du compte
- Lancement direct : synchro des repos faite, sans worktree

### Windows Terminal

Le raccourci lance `wt -w claude-launcher new-tab -p "Claude Code"` (nouvel onglet) ou `wt -w new new-tab -p "Claude Code"` (nouvelle fenêtre), selon le choix fait à l'installation, via `pythonw` (sans console) : épinglée, une cible `wt.exe` (alias d'exécution de `WindowsApps`) donne une icône grise. Sans `pythonw`, il cible `wt.exe` directement.

- 🪟 Mode onglet : chaque lancement ouvre un **nouvel onglet** dans la fenêtre nommée `claude-launcher`, créée si elle n'existe pas. Mode fenêtre : chaque lancement ouvre une **nouvelle fenêtre**
- 🛡️ Les **autres fenêtres** Windows Terminal ne reçoivent jamais d'onglet du launcher
- ⌨️ Avec une touche globale sur le raccourci, un nouveau launcher s'ouvre même pendant une session Claude
- 🔄 Chaque onglet fait sa propre [synchro des repos](#mises-à-jour-au-démarrage)
- ❌ L'onglet se ferme à la fin de la session (il reste ouvert si le launcher échoue)

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

Liste : le titre `★ Favorites` et les **favoris** du compte (`nom  (dossier parent)`, triés par nom), une ligne vide, le titre `Subfolders` et les **sous-dossiers** du dossier courant par ordre alphabétique, puis `+ New folder`. Les titres et la ligne vide ne sont jamais sélectionnables. Sans favori (ou sans favori correspondant au filtre), le titre `★ Favorites`, les favoris et la ligne vide sont masqués. Dossier inaccessible : message `Access denied`, on reste sur place.

| Touche | Action |
|--------|--------|
| `↑` `↓` | Sélectionner un dossier |
| `→` | Entrer dans le dossier |
| `←` | Remonter au dossier parent (le dossier quitté reste sélectionné) |
| Lettres | **Filtrer** favoris et sous-dossiers par nom (affiché `[filter: …]`) |
| `Retour arrière` | Effacer le dernier caractère du filtre |
| `Ctrl+F` | Ajouter ou retirer le dossier sélectionné des **favoris** du compte (ignoré sur `+ New folder`) |
| `Tab` | Changer de [session](#session) |
| `Entrée` | **Lancer Claude Code**, après le [choix du worktree](#choix-du-worktree) dans un repo git (ou créer un dossier sur `+ New folder`) |
| `Échap` | Vider le filtre, sinon revenir au choix du compte |
| `Ctrl+C` | Quitter |

- ⭐ **Favoris** : propres à chaque compte, sans limite, enregistrés aussitôt. Un favori aussi présent dans les sous-dossiers du dossier courant est listé dans les deux sections. Après `Ctrl+F` sur un sous-dossier, il reste sélectionné ; après avoir retiré un favori, la sélection passe au favori suivant (sinon au précédent, sinon au premier sous-dossier). Pas de favoris dans le choix du dossier par défaut
- ❓ Un favori dont le dossier n'existe plus reste listé avec `(missing)` en gris : `Entrée` affiche `Folder not found.` sans lancer, `Ctrl+F` le retire. Il n'est jamais retiré automatiquement
- 📁 `+ New folder` : demande un nom (pré-rempli avec le filtre), crée le dossier dans le dossier courant puis le sélectionne
- 🪟 Titre de l'onglet : `Claude Code · <compte> · <projet>` au lancement, puis Claude Code le remplace par `✳ <sujet>`, animé pendant le traitement

#### Session

Ligne `Session` de l'en-tête, `Tab` passe à la suivante :

| Session | Commande |
|---------|----------|
| `new conversation` | `claude` |
| `continue the last conversation` | `claude --continue` |
| `resume a conversation, picked in Claude Code` | `claude --resume` |

### Choix du worktree

Étape affichée après le choix du dossier, **seulement s'il est dans un repo git**. Liste : `No worktree` (sélectionné par défaut : lance dans le dossier choisi, comme avant), les worktrees du repo triés par nom (`nom  from <branche d'origine>`), puis `+ Worktree`.

| Touche | Action |
|--------|--------|
| `↑` `↓` | Sélectionner une ligne |
| `Tab` | Changer de [session](#session) |
| `Entrée` | **Lancer Claude Code** dans le dossier ou le worktree (ou créer un worktree sur `+ Worktree`) |
| `Échap` | Revenir au choix du dossier (le dossier reste sélectionné) |
| `Ctrl+C` | Quitter |

- 🌳 `+ Worktree` : nom du worktree, puis branche d'origine choisie dans une liste, puis lancement de Claude Code dans `~/.claude-worktrees/<id>/<nom>/`, sur une nouvelle branche `temp/<nom>`
- 🌿 **Branches d'origine** : les branches **favorites** du repo en haut (`★ Favorites`), puis toutes ses branches, locales puis distantes sans branche locale (`temp/*` exclues). Les caractères tapés filtrent la liste, `Retour arrière` en efface un, `Échap` vide le filtre (ou revient en arrière s'il est vide) et `Ctrl+F` ajoute ou retire la branche sélectionnée des favoris. Une branche distante choisie crée d'abord la branche locale qui la suit. La liste se met à jour d'elle-même à la fin du `git fetch --prune` lancé à l'ouverture de l'étape : une branche poussée juste avant apparaît, la sélection reste sur la même branche
- 🔗 **Origine = upstream** : `temp/<nom>` est créée avec sa branche d'origine pour upstream (`git worktree add --track`), donc `git rev-parse --abbrev-ref temp/<nom>@{upstream}` la donne à n'importe quel outil, sans passer par le launcher
- ✅ **Marqueur `merged`** : à l'ouverture de l'étape, un `git fetch --prune` part en arrière-plan sans retarder l'affichage et met à jour les branches distantes pour l'ouverture suivante. Un worktree dont la branche d'origine suit une branche distante supprimée est marqué `merged` (`nom  from <origine> · merged`), y compris après un squash merge. Chaque ordinateur sait ainsi quels worktrees nettoyer
- 💬 **Historique partagé** : l'historique des conversations d'un worktree est celui du dossier principal du repo. Au lancement dans un worktree avec un compte, `projects/<chemin du worktree encodé>` du compte est une jonction vers `projects/<chemin du repo encodé>` (créée avec sa cible si besoin, un vrai dossier existant n'est jamais touché), donc `continue the last conversation` depuis le dossier principal retrouve aussi les conversations des worktrees. Dans un worktree, `continue the last conversation` reprend la dernière conversation lancée dans ce worktree (`--resume <id de session>`), sinon une nouvelle conversation. L'historique des worktrees créés avant ce changement n'est pas migré
- 🧹 À l'ouverture de l'étape : les worktrees dont le dossier a été supprimé sont retirés (`git worktree prune`, leur branche `temp/` est gardée), les dossiers vides restés dans `~/.claude-worktrees/<id>/` (worktree supprimé pendant que Claude Code tournait dedans) sont supprimés, et les jonctions d'historique des worktrees que git ne connaît plus sont retirées (l'historique pointé est gardé). Un dossier non vide n'est jamais touché
- 🪟 Titre de l'onglet : `Claude Code · <compte> · <projet> · <worktree>`

> [!IMPORTANT]
> - Terminer ou supprimer un worktree se fait **hors du launcher**, avec git ou depuis Claude Code. Le launcher ne **pousse jamais** rien.

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
| `Delete account` | Déconnecte, retire les jonctions et supprime dossier, réglages et favoris (après confirmation) |

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
| 1 | Changements non commités | `N changed files, commit & push?` (fichiers listés au-dessus) | `git add --all` + commit (message modifiable) |
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
| `install.ps1` | Raccourci, profil Windows Terminal, repo de skills, `CLAUDE.md` global |
| `uninstall.ps1` | Suppression du raccourci, du profil Windows Terminal, de la config et des comptes |
| `launcher/paths.py` | Chemins utilisés (repo, `config.json`, `~/.claude-accounts`, `~/.claude`) |
| `launcher/repo_sync.py` | Synchro des repos au démarrage |
| `launcher/git_repo.py` | Commandes git (fetch, pull, merge, commit, push) |
| `launcher/accounts.py` | Comptes : dossiers, jonctions, commande de lancement |
| `launcher/launcher_state.py` | `launcher_state.json` : nom, dossier par défaut, favoris |
| `launcher/account_menu.py` | Menu des comptes et options |
| `launcher/folder_menu.py` | Choix du dossier : filtre, nouveau dossier, session |
| `launcher/worktree_menu.py` | Choix du worktree : liste, choix de la branche d'origine avec favoris |
| `launcher/worktrees.py` | Worktrees : création, liste, origine, détection `merged`, nettoyage des dossiers vides (commandes git) |
| `launcher/history.py` | Historique des conversations : dossier d'un chemin, jonction d'un worktree, dernière session, nettoyage des jonctions |
| `launcher/junctions.py` | Création des jonctions de dossier |
| `launcher/worktrees_state.py` | `worktrees_state.json` : id du dossier des worktrees et branches favorites, par repo |
| `launcher/json_store.py` | Lecture et écriture atomique des fichiers JSON d'état |
| `launcher/prompts.py` | Questions `Y/N`, messages de commit, noms de compte et de dossier |
| `launcher/keyboard.py` | Lecture du clavier |
| `launcher/terminal_ui.py` | Rendu console : en-tête, listes, messages |
| `tests/` | Tests des worktrees sur de vrais repos temporaires : `python -m unittest discover -s tests -v` |

## Fichiers locaux

Non versionnés (`.gitignore`), propres à chaque machine :

| Fichier | Rôle |
|---------|------|
| `*.lnk` | Raccourcis générés par `install.ps1` |
| `config.json` | Chemin du repo de skills (`skills_repo`, `null` si désactivé) |

Hors du repo, dans le dossier utilisateur :

| Dossier | Rôle |
|---------|------|
| `~/.claude-accounts/` | Comptes et `launcher_state.json` |
| `~/.claude-worktrees/` | Worktrees (`<id>/<nom>/`, un id par repo) et `worktrees_state.json` (`{"repos": {"<racine du repo>": {"id": "<hex>", "favorite_branches": ["dev", "origin/stage"]}}}`) |
