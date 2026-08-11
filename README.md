# Réducteur de couleurs

Application de bureau (Tkinter) pour réduire le nombre de couleurs d'une image
par quantification K-means et exporter le résultat en PNG palettisé.

## Installation

```bash
pip install pillow numpy scikit-learn
```

## Lancer l'application

```bash
python3 app.py
```

## Utilisation

1. Importer une image (JPG, PNG, WEBP).
2. Ajuster le nombre de couleurs et l'échelle avec les sliders.
3. L'aperçu se met à jour automatiquement.
4. Exporter le résultat en PNG.

## Fichiers

- `app.py` — interface graphique Tkinter.
- `engine.py` — traitement d'image (palette K-means, quantification, export PNG palettisé).
