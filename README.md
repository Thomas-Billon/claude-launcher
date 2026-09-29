# claude-launcher

Sélecteur de dossier interactif qui lance Claude Code dans le projet choisi.

Le launcher liste les sous-dossiers d'un répertoire racine, trie en tête les dossiers lancés le plus récemment, puis exécute `claude` dans le dossier sélectionné.

## Prérequis

- Windows (le launcher lit le clavier via `msvcrt`)
- Python 3 dans le `PATH`
- Claude Code CLI (`claude`) dans le `PATH`

## Installation

1. Copier `claude_launcher.config.example.json` en `claude_launcher.config.json` et y renseigner le dossier racine des projets :

   ```json
   {
     "target_dir": "C:\\Path\\To\\Projects"
   }
   ```

   Sans ce fichier, le launcher part du dossier utilisateur.

2. Créer le raccourci « Claude Code » dans le menu Démarrer :

   ```powershell
   ./install.ps1
   ```

   Les chemins du raccourci sont déduits de l'emplacement du repo : relancer le script après un déplacement du repo ou sur une nouvelle machine. Le raccourci peut ensuite être épinglé à la barre des tâches.

## Utilisation

Via le raccourci du menu Démarrer, ou en ligne de commande :

```powershell
python claude_launcher.py                  # dossier racine de la config
python claude_launcher.py -d <dossier>     # dossier racine ponctuel
```

| Touche | Action |
|--------|--------|
| ↑ / ↓ | Sélectionner un dossier |
| → | Entrer dans le dossier sélectionné |
| ← | Remonter au dossier parent |
| Entrée | Lancer Claude Code dans le dossier sélectionné |
| Échap / Ctrl+C | Quitter |

## Fichiers locaux

Non versionnés (`.gitignore`), propres à chaque machine :

| Fichier | Rôle |
|---------|------|
| `claude_launcher.config.json` | Dossier racine des projets |
| `claude_launcher_history.json` | Date du dernier lancement par dossier, pour le tri |
| `*.lnk` | Raccourcis générés par `install.ps1` |
