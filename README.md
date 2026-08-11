# Réducteur de couleurs

Application de bureau (Tkinter) pour réduire le nombre de couleurs d'une image
par quantification K-means et exporter le résultat en PNG palettisé.

## Installation

```bash
pip install pillow numpy scikit-learn scipy
```

## Lancer l'application

```bash
python3 app.py
```

## Utilisation

1. Importer une image (JPG, PNG, WEBP).
2. Ajuster le nombre de couleurs et les dimensions (largeur/hauteur en pixels)
   avec les sliders ou en tapant une valeur / en utilisant les flèches.
3. Cocher "Conserver les proportions" pour lier largeur et hauteur, ou la
   décocher pour les régler indépendamment (déformation possible).
4. Cocher "Dithering (Floyd-Steinberg)" pour diffuser l'erreur de
   quantification et réduire le banding (plus lent, surtout à l'export).
5. L'aperçu et la palette de couleurs utilisée se mettent à jour automatiquement.
6. Exporter le résultat en PNG.

## Fichiers

- `app.py` — interface graphique Tkinter.
- `engine.py` — traitement d'image (palette K-means, quantification directe ou
  avec dithering Floyd-Steinberg, export PNG palettisé).
