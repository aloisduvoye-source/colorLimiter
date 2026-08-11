import colorsys
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

def compute_palette(pixels_rgb, n_colors, sample_size=100_000):
    """Calcule une palette de N couleurs par K-means."""
    total = len(pixels_rgb)
    
    if total <= n_colors:
        return np.unique(pixels_rgb, axis=0)
    
    # Échantillonnage
    if total > sample_size:
        rng = np.random.default_rng(42)
        indices = rng.choice(total, size=sample_size, replace=False)
        training = pixels_rgb[indices]
    else:
        training = pixels_rgb
    
    kmeans = KMeans(n_clusters=n_colors, n_init=3, random_state=42, max_iter=100)
    kmeans.fit(training)
    
    palette = np.rint(kmeans.cluster_centers_).clip(0, 255).astype(np.uint8)
    return palette

def sort_palette(palette):
    """Trie la palette par teinte puis par luminosité (HSL), pour un affichage lisible."""
    def key(color):
        h, l, _s = colorsys.rgb_to_hls(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
        return (h, l)

    order = sorted(range(len(palette)), key=lambda i: key(palette[i]))
    return palette[order]

def quantize_image(pixels_rgb, palette, block_size=1_000_000, progress_callback=None):
    """Quantifie chaque pixel vers la couleur la plus proche dans la palette."""
    total = len(pixels_rgb)
    labels = np.empty(total, dtype=np.uint8)

    for start in range(0, total, block_size):
        end = min(start + block_size, total)
        block = pixels_rgb[start:end]
        distances = np.sum((block[:, None, :].astype(np.float32) -
                           palette[None, :, :].astype(np.float32)) ** 2, axis=2)
        labels[start:end] = np.argmin(distances, axis=1)
        if progress_callback:
            progress_callback(end / total)

    return labels

def build_color_lut(palette, levels=32):
    """Précalcule, pour une grille de couleurs quantifiées (levels par canal),
    l'indice de palette le plus proche. Remplace une recherche cKDTree par pixel
    (coûteuse en appels de fonction) par un simple indexage de tableau."""
    step = 256.0 / levels
    centers = (np.arange(levels) + 0.5) * step
    r, g, b = np.meshgrid(centers, centers, centers, indexing="ij")
    grid = np.stack([r.ravel(), g.ravel(), b.ravel()], axis=1).astype(np.float32)
    palette_f = palette.astype(np.float32)
    distances = np.sum((grid[:, None, :] - palette_f[None, :, :]) ** 2, axis=2)
    lut = np.argmin(distances, axis=1).astype(np.uint8).reshape(levels, levels, levels)
    return lut, step

def dither_image(pixels_rgb, palette, width, height, progress_callback=None):
    """Quantifie chaque pixel vers la couleur la plus proche dans la palette,
    en diffusant l'erreur de quantification (Floyd-Steinberg).
    La boucle travaille sur des listes/floats Python natifs plutôt que sur des
    scalaires numpy : chaque accès/opération numpy a un coût d'appel fixe non
    négligeable répété des millions de fois, alors que les flottants Python natifs
    évitent cet overhead (~10x plus rapide en pratique)."""
    lut, step = build_color_lut(palette)
    levels = lut.shape[0]
    lut_list = lut.tolist()
    palette_list = palette.astype(np.float64).tolist()

    work = pixels_rgb.astype(np.float64).reshape(height, width, 3).tolist()
    labels = [[0] * width for _ in range(height)]

    # Reporter la progression au maximum ~200 fois pour ne pas ralentir la boucle
    report_every = max(1, height // 200)
    w7, w3, w5, w1 = 7 / 16, 3 / 16, 5 / 16, 1 / 16

    for y in range(height):
        row = work[y]
        next_row = work[y + 1] if y + 1 < height else None
        labels_row = labels[y]
        for x in range(width):
            pr, pg, pb = row[x]

            ri = int(pr / step)
            if ri < 0:
                ri = 0
            elif ri >= levels:
                ri = levels - 1
            gi = int(pg / step)
            if gi < 0:
                gi = 0
            elif gi >= levels:
                gi = levels - 1
            bi = int(pb / step)
            if bi < 0:
                bi = 0
            elif bi >= levels:
                bi = levels - 1

            idx = lut_list[ri][gi][bi]
            labels_row[x] = idx
            cr, cg, cb = palette_list[idx]
            er, eg, eb = pr - cr, pg - cg, pb - cb

            if x + 1 < width:
                nr, ng, nb = row[x + 1]
                row[x + 1] = (nr + er * w7, ng + eg * w7, nb + eb * w7)
            if next_row is not None:
                if x > 0:
                    nr, ng, nb = next_row[x - 1]
                    next_row[x - 1] = (nr + er * w3, ng + eg * w3, nb + eb * w3)
                nr, ng, nb = next_row[x]
                next_row[x] = (nr + er * w5, ng + eg * w5, nb + eb * w5)
                if x + 1 < width:
                    nr, ng, nb = next_row[x + 1]
                    next_row[x + 1] = (nr + er * w1, ng + eg * w1, nb + eb * w1)

        if progress_callback and (y % report_every == 0 or y == height - 1):
            progress_callback((y + 1) / height)

    return np.array(labels, dtype=np.uint8).reshape(-1)

def create_paletted_image(width, height, labels, palette, alpha=None):
    """Crée une image palettisée PNG avec transparence optionnelle."""
    indexed = labels.reshape(height, width)
    img = Image.fromarray(indexed, mode="P")
    
    flat_palette = palette.flatten().tolist()
    flat_palette += [0] * (256 * 3 - len(flat_palette))
    img.putpalette(flat_palette)
    
    if alpha is not None:
        n_colors = len(palette)
        alpha_flat = alpha.reshape(-1)
        alpha_palette = np.zeros(n_colors, dtype=np.uint8)
        for i in range(n_colors):
            mask = labels == i
            if np.any(mask):
                alpha_palette[i] = int(np.rint(alpha_flat[mask].mean()))
        img.info["transparency"] = bytes(alpha_palette.tolist() + [255] * (256 - n_colors))
    
    return img

def process_image(image, n_colors, size=None, sample_size=100_000, dither=False,
                   progress_callback=None, palette=None):
    """
    Traite une image PIL complète.
    Redimensionne vers `size` (largeur, hauteur) si fourni.
    Si `dither` est vrai, applique un dithering Floyd-Steinberg au lieu
    d'une quantification directe (plus lent, réduit le banding).
    Si `palette` est fournie (tableau (N, 3) uint8), elle est utilisée telle quelle
    (sans recalcul K-means ni tri) — utile pour une palette éditée manuellement.
    `progress_callback(fraction)` est appelé avec une valeur entre 0.0 et 1.0.
    Retourne (image_palettisée, palette) où palette est un tableau (N, 3) de couleurs RGB.
    """
    def report(fraction):
        if progress_callback:
            progress_callback(fraction)

    has_alpha = "A" in image.getbands()
    img = image.convert("RGBA") if has_alpha else image.convert("RGB")

    # Redimensionnement si nécessaire
    if size is not None and size != img.size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    report(0.05)

    width, height = img.size
    pixels = np.asarray(img)

    rgb = pixels[:, :, :3]
    alpha = pixels[:, :, 3] if has_alpha else None
    pixels_rgb = rgb.reshape(-1, 3)

    if palette is None:
        palette = compute_palette(pixels_rgb, n_colors, sample_size)
        palette = sort_palette(palette)
    else:
        palette = np.asarray(palette, dtype=np.uint8)
    report(0.3)

    step_progress = lambda f: report(0.3 + f * 0.65)
    if dither:
        labels = dither_image(pixels_rgb, palette, width, height,
                               progress_callback=step_progress)
    else:
        labels = quantize_image(pixels_rgb, palette, progress_callback=step_progress)

    result = create_paletted_image(width, height, labels, palette, alpha)
    report(1.0)
    return result, palette