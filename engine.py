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

def quantize_image(pixels_rgb, palette, block_size=1_000_000):
    """Quantifie chaque pixel vers la couleur la plus proche dans la palette."""
    total = len(pixels_rgb)
    labels = np.empty(total, dtype=np.uint8)
    
    for start in range(0, total, block_size):
        end = min(start + block_size, total)
        block = pixels_rgb[start:end]
        distances = np.sum((block[:, None, :].astype(np.float32) - 
                           palette[None, :, :].astype(np.float32)) ** 2, axis=2)
        labels[start:end] = np.argmin(distances, axis=1)
    
    return labels

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

def process_image(image, n_colors, scale=1.0, sample_size=100_000):
    """
    Traite une image PIL complète.
    Retourne l'image palettisée redimensionnée si scale != 1.0.
    """
    has_alpha = "A" in image.getbands()
    img = image.convert("RGBA") if has_alpha else image.convert("RGB")
    
    # Redimensionnement si nécessaire
    if scale != 1.0:
        w, h = img.size
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    width, height = img.size
    pixels = np.asarray(img)
    
    rgb = pixels[:, :, :3]
    alpha = pixels[:, :, 3] if has_alpha else None
    pixels_rgb = rgb.reshape(-1, 3)
    
    palette = compute_palette(pixels_rgb, n_colors, sample_size)
    labels = quantize_image(pixels_rgb, palette)
    
    return create_paletted_image(width, height, labels, palette, alpha)