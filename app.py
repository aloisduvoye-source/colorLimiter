#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageChops
import numpy as np
import colorsys
import threading
import os

from engine import process_image

class ColorReducerApp:
    def __init__(self, root):
        self.root = root
        root.title("Réducteur de couleurs")
        root.geometry("1000x700")
        root.minsize(800, 600)
        self._set_app_icon()

        self.input_path = None
        self.original_image = None
        self.processed_image = None  # Image traitée (PIL)
        self.current_palette = None  # Palette (N, 3) de la dernière image traitée
        self.custom_palette = None  # Si défini, palette éditée à la main (remplace le calcul K-means)
        self.export_progress = tk.DoubleVar(value=0)
        self._orig_display_rect = None  # (x, y, ratio) de l'image affichée dans le canvas original
        self._preview_display_rect = None  # idem pour le canvas aperçu

        # Variables pour les sliders
        self.n_colors = tk.IntVar(value=16)
        self.width_var = tk.IntVar(value=0)
        self.height_var = tk.IntVar(value=0)
        self.keep_aspect = tk.BooleanVar(value=True)
        self.dither_var = tk.BooleanVar(value=False)
        self._aspect_ratio = 1.0
        self._syncing_dims = False
        
        self.setup_ui()

        # Forcer un premier redimensionnement après l'affichage
        self.root.update_idletasks()
        self.root.after(100, self.resize_images)

    @staticmethod
    def _round_corners(image, radius_ratio=0.22, supersample=4):
        """Applique des coins arrondis anti-aliasés à une image carrée (calcul en
        surrésolution puis réduction, pour un contour lisse plutôt que crénelé)."""
        image = image.convert("RGBA")
        w, h = image.size
        big = image.resize((w * supersample, h * supersample), Image.LANCZOS)

        mask = Image.new("L", big.size, 0)
        radius = int(min(big.size) * radius_ratio)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, big.size[0] - 1, big.size[1] - 1], radius=radius, fill=255)

        # Intersecte avec la transparence déjà présente dans l'image source
        combined_alpha = ImageChops.darker(big.split()[3], mask)
        big.putalpha(combined_alpha)

        return big.resize((w, h), Image.LANCZOS)

    def _set_app_icon(self):
        """Charge l'icône depuis public/icon.png (si présente), lui applique des coins
        arrondis et la décline en plusieurs tailles standard pour un rendu net dans
        la barre des tâches / le dock, quelle que soit la taille utilisée par l'OS."""
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "icon.png")
        if not os.path.isfile(icon_path):
            return
        try:
            source = self._round_corners(Image.open(icon_path))
            sizes = [64, 48, 32, 16]
            self._icon_images = [
                ImageTk.PhotoImage(source.resize((s, s), Image.LANCZOS)) for s in sizes]
            self.root.iconphoto(True, *self._icon_images)
        except Exception:
            pass

    def setup_ui(self):
        # Frame principal
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Ligne d'import
        top_frame = ttk.Frame(main)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(top_frame, text="📂 Importer une image", 
                   command=self.load_image).pack(side=tk.LEFT, padx=(0, 10))
        
        self.file_label = ttk.Label(top_frame, text="Aucun fichier", foreground="gray")
        self.file_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Panneau palette (intégré, toujours affiché, en haut de l'écran)
        self.palette_frame = ttk.LabelFrame(main, text="Palette utilisée", padding=5)
        self.palette_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(self.palette_frame,
                  text="Clic gauche : modifier une couleur · Clic droit : la supprimer · + : en ajouter une",
                  foreground="gray", font=("TkDefaultFont", 8)).pack(anchor="w", pady=(0, 3))
        self.palette_canvas = tk.Canvas(self.palette_frame, height=100, highlightthickness=0)
        palette_scrollbar = ttk.Scrollbar(
            self.palette_frame, orient="vertical", command=self.palette_canvas.yview)
        self.palette_swatches_frame = ttk.Frame(self.palette_canvas)

        self.palette_swatches_frame.bind(
            "<Configure>",
            lambda e: self.palette_canvas.configure(scrollregion=self.palette_canvas.bbox("all")))
        self._palette_window_id = self.palette_canvas.create_window(
            (0, 0), window=self.palette_swatches_frame, anchor="nw")
        # La frame interne épouse toute la largeur du canvas ; le nombre de
        # colonnes de pastilles (carrées, taille fixe) est recalculé pour
        # que les lignes remplissent au mieux cette largeur
        self.palette_canvas.bind("<Configure>", self._on_palette_canvas_resize)
        self.palette_canvas.configure(yscrollcommand=palette_scrollbar.set)

        self.palette_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        palette_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.refresh_palette_display()

        # Frame des images (côte à côte)
        self.images_frame = ttk.Frame(main)
        self.images_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Original
        left_panel = ttk.LabelFrame(self.images_frame, text="Original", padding=5)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Canvas avec gestion du redimensionnement
        self.original_canvas = tk.Canvas(left_panel, bg="#2e2e2e", highlightthickness=0)
        self.original_canvas.pack(fill=tk.BOTH, expand=True)
        self.original_canvas.bind("<Configure>", lambda e: self.resize_original())
        
        # Résultat
        right_panel = ttk.LabelFrame(self.images_frame, text="Aperçu (PNG palettisé)", padding=5)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.preview_canvas = tk.Canvas(right_panel, bg="#2e2e2e", highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Configure>", lambda e: self.resize_preview())
        
        # Contrôles
        controls = ttk.LabelFrame(main, text="Paramètres", padding=10)
        controls.pack(fill=tk.X, pady=10)
        
        # Slider couleurs (+ édition manuelle via champ/flèches)
        vcmd = (self.root.register(self._validate_digits), "%P")

        color_frame = ttk.Frame(controls)
        color_frame.pack(fill=tk.X, pady=2)
        ttk.Label(color_frame, text="Couleurs :").pack(side=tk.LEFT)
        ttk.Scale(color_frame, from_=2, to=256, orient=tk.HORIZONTAL,
                  variable=self.n_colors, command=self.on_n_colors_change).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.color_spin = ttk.Spinbox(
            color_frame, from_=2, to=256, width=6, textvariable=self.n_colors,
            validate="key", validatecommand=vcmd, command=self.on_any_change)
        self.color_spin.pack(side=tk.LEFT)
        self.color_spin.bind("<Return>", self.on_any_change)
        self.color_spin.bind("<FocusOut>", self.on_any_change)

        # Sliders largeur / hauteur

        width_frame = ttk.Frame(controls)
        width_frame.pack(fill=tk.X, pady=2)
        ttk.Label(width_frame, text="Largeur :").pack(side=tk.LEFT)
        ttk.Scale(width_frame, from_=10, to=8000, orient=tk.HORIZONTAL,
                  variable=self.width_var,
                  command=lambda v: self.on_dimension_change("width")).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.width_spin = ttk.Spinbox(
            width_frame, from_=10, to=8000, width=6, textvariable=self.width_var,
            validate="key", validatecommand=vcmd,
            command=lambda: self.on_dimension_change("width"))
        self.width_spin.pack(side=tk.LEFT)
        self.width_spin.bind("<Return>", lambda e: self.on_dimension_change("width"))
        self.width_spin.bind("<FocusOut>", lambda e: self.on_dimension_change("width"))
        ttk.Label(width_frame, text="px").pack(side=tk.LEFT, padx=(3, 0))

        height_frame = ttk.Frame(controls)
        height_frame.pack(fill=tk.X, pady=2)
        ttk.Label(height_frame, text="Hauteur :").pack(side=tk.LEFT)
        ttk.Scale(height_frame, from_=10, to=8000, orient=tk.HORIZONTAL,
                  variable=self.height_var,
                  command=lambda v: self.on_dimension_change("height")).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.height_spin = ttk.Spinbox(
            height_frame, from_=10, to=8000, width=6, textvariable=self.height_var,
            validate="key", validatecommand=vcmd,
            command=lambda: self.on_dimension_change("height"))
        self.height_spin.pack(side=tk.LEFT)
        self.height_spin.bind("<Return>", lambda e: self.on_dimension_change("height"))
        self.height_spin.bind("<FocusOut>", lambda e: self.on_dimension_change("height"))
        ttk.Label(height_frame, text="px").pack(side=tk.LEFT, padx=(3, 0))

        # Options
        opt_frame = ttk.Frame(controls)
        opt_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(opt_frame, text="Conserver les proportions",
                        variable=self.keep_aspect,
                        command=self.on_keep_aspect_toggle).pack(side=tk.LEFT)
        ttk.Checkbutton(opt_frame, text="Dithering (Floyd-Steinberg)",
                        variable=self.dither_var,
                        command=self.on_any_change).pack(side=tk.LEFT, padx=(15, 0))
        
        # Boutons d'action
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="🔄 Réinitialiser",
                   command=self.reset).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🎲 Générer palette auto",
                   command=self.generate_auto_palette).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="💾 Exporter en PNG",
                   command=self.export).pack(side=tk.RIGHT, padx=5)

        # Barre de progression / statut
        self.status = ttk.Label(main, text="Prêt", foreground="gray")
        self.status.pack(fill=tk.X, pady=(5, 0))

        self.export_progress_bar = ttk.Progressbar(
            main, variable=self.export_progress, maximum=100, mode="determinate")

    @staticmethod
    def _validate_digits(value):
        return value == "" or value.isdigit()

    def on_keep_aspect_toggle(self):
        """Si on réactive la conservation des proportions, réaligne la hauteur sur la largeur."""
        if self.keep_aspect.get() and self._aspect_ratio:
            self.on_dimension_change("width")

    def on_dimension_change(self, source):
        """Synchronise largeur/hauteur si 'Conserver les proportions' est actif, puis relance l'aperçu."""
        if self._syncing_dims or not self.original_image:
            return
        try:
            w = self.width_var.get()
            h = self.height_var.get()
        except tk.TclError:
            return
        if w <= 0 or h <= 0:
            return

        self._syncing_dims = True
        try:
            # Nettoie la valeur flottante brute que ttk.Scale peut écrire dans la variable
            if source == "width":
                self.width_var.set(w)
            else:
                self.height_var.set(h)

            if self.keep_aspect.get() and self._aspect_ratio:
                if source == "width":
                    self.height_var.set(max(1, round(w / self._aspect_ratio)))
                else:
                    self.width_var.set(max(1, round(h * self._aspect_ratio)))
        finally:
            self._syncing_dims = False

        self.on_any_change()

    def load_image(self):
        path = filedialog.askopenfilename(
            title="Choisir une image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")]
        )
        if not path:
            return
            
        self.input_path = path
        self.file_label.config(text=os.path.basename(path), foreground="black")
        
        try:
            self.original_image = Image.open(path)
            self.processed_image = None

            w, h = self.original_image.size
            self._aspect_ratio = w / h
            self._syncing_dims = True
            self.width_var.set(w)
            self.height_var.set(h)
            self._syncing_dims = False

            self.resize_original()
            self.update_preview()
            self.status.config(text="Image chargée", foreground="green")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir l'image : {e}")
            self.status.config(text="Erreur", foreground="red")
    
    @staticmethod
    def _fit_image(image, width, height):
        """Redimensionne l'image (agrandit ou réduit) pour occuper le maximum
        d'espace dans width x height, en conservant les proportions."""
        ratio = min(width / image.width, height / image.height)
        new_size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
        resample = Image.Resampling.LANCZOS if ratio < 1 else Image.Resampling.BICUBIC
        return image.resize(new_size, resample)

    def resize_original(self):
        """Redimensionne l'image originale pour remplir le canvas."""
        if not self.original_image:
            return
            
        # Récupérer la taille du canvas
        width = self.original_canvas.winfo_width()
        height = self.original_canvas.winfo_height()
        
        if width < 10 or height < 10:
            return
            
        # Copier et redimensionner (agrandit ou réduit pour remplir le cadre)
        display = self._fit_image(self.original_image, width, height)

        # Centrer dans le canvas
        self.orig_tk = ImageTk.PhotoImage(display)
        self.original_canvas.delete("all")

        x = (width - display.width) // 2
        y = (height - display.height) // 2
        self.original_canvas.create_image(x, y, image=self.orig_tk, anchor="nw")
        # Rectangle d'affichage (pour retrouver le pixel image cliqué, ex. pipette)
        self._orig_display_rect = (x, y, display.width / self.original_image.width)
        
    def resize_preview(self):
        """Redimensionne l'image traitée pour remplir le canvas."""
        if not self.processed_image:
            # Afficher un message "En attente" si aucune image
            self.preview_canvas.delete("all")
            width = self.preview_canvas.winfo_width()
            height = self.preview_canvas.winfo_height()
            if width > 100 and height > 100:
                self.preview_canvas.create_text(
                    width//2, height//2,
                    text="Aucun aperçu",
                    fill="#666",
                    font=("Arial", 14)
                )
            return
            
        # Récupérer la taille du canvas
        width = self.preview_canvas.winfo_width()
        height = self.preview_canvas.winfo_height()
        
        if width < 10 or height < 10:
            return
            
        # Copier et redimensionner (agrandit ou réduit pour remplir le cadre)
        display = self._fit_image(self.processed_image, width, height)

        # Centrer dans le canvas
        self.preview_tk = ImageTk.PhotoImage(display)
        self.preview_canvas.delete("all")

        x = (width - display.width) // 2
        y = (height - display.height) // 2
        self.preview_canvas.create_image(x, y, image=self.preview_tk, anchor="nw")
        # Rectangle d'affichage (pour retrouver le pixel image cliqué, ex. pipette)
        self._preview_display_rect = (x, y, display.width / self.processed_image.width)
        
    def resize_images(self):
        """Redimensionne les deux images en réponse à un changement de taille."""
        self.resize_original()
        self.resize_preview()
        
    def on_any_change(self, *args):
        """Déclenche la mise à jour de l'aperçu avec debounce."""
        if hasattr(self, "_after_id"):
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(200, self.update_preview)

    def on_n_colors_change(self, value):
        """Arrondit la valeur du slider (ttk.Scale ne s'arrête que sur des entiers via IntVar,
        mais peut écrire une valeur flottante brute dans la variable Tk)."""
        self.n_colors.set(round(float(value)))
        self.on_any_change()

    def update_preview(self):
        """Lance le traitement en arrière-plan."""
        if not self.original_image:
            return
            
        # Désactiver les contrôles pendant le traitement
        self.status.config(text="Traitement en cours...", foreground="orange")
        self.root.config(cursor="watch")
        
        def task():
            try:
                n = self.n_colors.get()
                target_w = self.width_var.get()
                target_h = self.height_var.get()
                dither = self.dither_var.get()

                # Aperçu limité à 800px sur le plus grand côté, mais toujours
                # aux proportions exactes de la taille cible (pas de la source)
                max_preview = 800
                cap = min(1.0, max_preview / target_w, max_preview / target_h)
                preview_size = (max(1, round(target_w * cap)),
                                 max(1, round(target_h * cap)))

                result, palette = process_image(
                    self.original_image, n, size=preview_size, dither=dither,
                    palette=self.custom_palette)

                self.root.after(0, lambda: self.set_processed_image(result, palette))
                self.root.after(0, lambda: self.status.config(
                    text=f"Aperçu généré avec {n} couleurs", foreground="green"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur", f"Échec du traitement : {e}"))
                self.root.after(0, lambda: self.status.config(
                    text="Erreur", foreground="red"))
            finally:
                self.root.after(0, lambda: self.root.config(cursor=""))
                
        threading.Thread(target=task, daemon=True).start()
        
    def set_processed_image(self, pil_image, palette):
        """Définit l'image traitée et la redimensionne."""
        self.processed_image = pil_image
        self.current_palette = palette
        self.resize_preview()
        self.refresh_palette_display()


    def export(self):
        """Exporte l'image finale en PNG."""
        if not self.original_image:
            messagebox.showwarning("Avertissement", "Veuillez d'abord importer une image.")
            return
            
        path = filedialog.asksaveasfilename(
            title="Exporter en PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")]
        )
        if not path:
            return
            
        self.status.config(text="Export en cours...", foreground="orange")
        self.root.config(cursor="watch")
        self.export_progress.set(0)
        self.export_progress_bar.pack(fill=tk.X, pady=(5, 0))

        def task():
            try:
                n = self.n_colors.get()
                target_w = self.width_var.get()
                target_h = self.height_var.get()
                dither = self.dither_var.get()

                last_reported = -1

                def on_progress(fraction):
                    nonlocal last_reported
                    pct = fraction * 100
                    if pct - last_reported >= 1 or pct >= 100:
                        last_reported = pct
                        self.root.after(0, lambda p=pct: self.export_progress.set(p))

                result, palette = process_image(
                    self.original_image, n, size=(target_w, target_h), dither=dither,
                    progress_callback=on_progress, palette=self.custom_palette)
                result.save(path, "PNG", optimize=False)

                def apply_palette():
                    self.current_palette = palette
                    self.refresh_palette_display()
                self.root.after(0, apply_palette)

                self.root.after(0, lambda: messagebox.showinfo(
                    "Succès", f"Image exportée : {path}"))
                self.root.after(0, lambda: self.status.config(
                    text=f"Exporté vers {os.path.basename(path)}", foreground="green"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur", f"Échec de l'export : {e}"))
                self.root.after(0, lambda: self.status.config(
                    text="Erreur", foreground="red"))
            finally:
                self.root.after(0, lambda: self.root.config(cursor=""))
                self.root.after(0, self.export_progress_bar.pack_forget)

        threading.Thread(target=task, daemon=True).start()

    def _on_palette_canvas_resize(self, event):
        """Adapte la largeur de la frame interne et recalcule le nombre de
        colonnes de pastilles (débounce pour éviter de reconstruire à chaque pixel)."""
        self.palette_canvas.itemconfig(self._palette_window_id, width=event.width)
        if hasattr(self, "_palette_resize_after_id"):
            self.root.after_cancel(self._palette_resize_after_id)
        self._palette_resize_after_id = self.root.after(100, self.refresh_palette_display)

    def refresh_palette_display(self):
        """Reconstruit les pastilles de couleurs (carrées) à partir de self.current_palette,
        avec un nombre de colonnes calculé pour remplir la largeur disponible.
        Chaque pastille est cliquable (édition/suppression) ; une tuile "+" permet d'ajouter
        une couleur tant qu'une image est chargée."""
        for widget in self.palette_swatches_frame.winfo_children():
            widget.destroy()

        n = len(self.current_palette) if self.current_palette is not None else 0

        if n == 0 and not self.original_image:
            self.palette_frame.config(text="Palette utilisée")
            ttk.Label(self.palette_swatches_frame, text="Aucune palette disponible pour le moment.",
                      foreground="gray").grid(row=0, column=0, padx=5, pady=5, sticky="w")
            return

        self.palette_frame.config(
            text=f"Palette utilisée ({n} couleurs)" if n else "Palette utilisée")

        swatch_size = 28
        pad = 2
        canvas_width = self.palette_canvas.winfo_width()
        if canvas_width <= 1:
            canvas_width = 400
        cols = max(1, canvas_width // (swatch_size + 2 * pad))

        for i in range(n):
            r, g, b = (int(v) for v in self.current_palette[i][:3])
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            swatch = tk.Frame(self.palette_swatches_frame, bg=hex_color,
                               width=swatch_size, height=swatch_size,
                               relief="solid", borderwidth=1, cursor="hand2")
            swatch.grid(row=i // cols, column=i % cols, padx=pad, pady=pad, sticky="w")
            swatch.bind("<Button-1>", lambda e, idx=i: self.edit_palette_color(idx))
            swatch.bind("<Button-3>", lambda e, idx=i: self.delete_palette_color(idx))

        if self.original_image:
            add_tile = tk.Frame(self.palette_swatches_frame, width=swatch_size, height=swatch_size,
                                 relief="ridge", borderwidth=1, cursor="hand2")
            add_tile.grid_propagate(False)
            add_tile.grid(row=n // cols, column=n % cols, padx=pad, pady=pad, sticky="w")
            add_label = tk.Label(add_tile, text="+", fg="gray", font=("TkDefaultFont", 14, "bold"))
            add_label.pack(expand=True, fill="both")
            add_tile.bind("<Button-1>", lambda e: self.add_palette_color())
            add_label.bind("<Button-1>", lambda e: self.add_palette_color())

    def pick_color_hsl(self, initial_rgb=(255, 255, 255), title="Choisir une couleur"):
        """Dialogue modal de sélection de couleur : carré Saturation/Luminosité cliquable
        + barre de teinte, avec sliders de précision en complément.
        Retourne un tuple (r, g, b) en 0-255, ou None si annulé."""
        SQ = 200        # taille affichée du carré S/L
        RES = 80        # résolution de calcul du dégradé (mise à l'échelle ensuite)
        HUE_H = 18       # hauteur de la barre de teinte

        r0, g0, b0 = (v / 255.0 for v in initial_rgb)
        h0, l0, s0 = colorsys.rgb_to_hls(r0, g0, b0)
        state = {"h": h0, "s": s0, "l": l0}
        chosen = {"rgb": tuple(initial_rgb)}
        images = {}  # garde une référence aux PhotoImage (sinon garbage-collectées)
        last_rendered_hue_deg = {"value": None}

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        sl_canvas = tk.Canvas(main, width=SQ, height=SQ, highlightthickness=1,
                               highlightbackground="#888", cursor="crosshair")
        sl_canvas.pack()
        sl_cursor = {"outer": None, "inner": None}

        hue_canvas = tk.Canvas(main, width=SQ, height=HUE_H, highlightthickness=1,
                                highlightbackground="#888", cursor="sb_h_double_arrow")
        hue_canvas.pack(pady=(6, 12))
        hue_cursor = {"line": None}

        info_frame = ttk.Frame(main)
        info_frame.pack(fill=tk.X)
        preview = tk.Frame(info_frame, width=40, height=40, relief="solid", borderwidth=1)
        preview.pack(side=tk.LEFT, padx=(0, 10))
        preview.pack_propagate(False)
        hex_label = ttk.Label(info_frame, text="", font=("Courier", 11))
        hex_label.pack(side=tk.LEFT)

        sliders_frame = ttk.Frame(main)
        sliders_frame.pack(fill=tk.X, pady=(12, 0))
        sliders_frame.columnconfigure(1, weight=1)

        hue_var = tk.DoubleVar(value=h0 * 360)
        sat_var = tk.DoubleVar(value=s0 * 100)
        light_var = tk.DoubleVar(value=l0 * 100)

        def render_hue_bar():
            img = Image.new("RGB", (SQ, 1))
            for x in range(SQ):
                r, g, b = colorsys.hls_to_rgb(x / SQ, 0.5, 1.0)
                img.putpixel((x, 0), (int(r * 255), int(g * 255), int(b * 255)))
            images["hue"] = ImageTk.PhotoImage(img.resize((SQ, HUE_H)))
            hue_canvas.create_image(0, 0, anchor="nw", image=images["hue"])

        def render_sl_square():
            deg = round(state["h"] * 360)
            if last_rendered_hue_deg["value"] == deg:
                return
            last_rendered_hue_deg["value"] = deg
            h = state["h"]
            img = Image.new("RGB", (RES, RES))
            px = img.load()
            for yi in range(RES):
                l = 1.0 - yi / (RES - 1)
                for xi in range(RES):
                    s = xi / (RES - 1)
                    r, g, b = colorsys.hls_to_rgb(h, l, s)
                    px[xi, yi] = (int(r * 255), int(g * 255), int(b * 255))
            images["sl"] = ImageTk.PhotoImage(img.resize((SQ, SQ), Image.NEAREST))
            sl_canvas.delete("bg")
            sl_canvas.create_image(0, 0, anchor="nw", image=images["sl"], tags="bg")
            sl_canvas.tag_lower("bg")

        def redraw_cursors():
            x, y = state["s"] * SQ, (1 - state["l"]) * SQ
            r = 5
            if sl_cursor["outer"] is None:
                sl_cursor["outer"] = sl_canvas.create_oval(0, 0, 0, 0, outline="black", width=1)
                sl_cursor["inner"] = sl_canvas.create_oval(0, 0, 0, 0, outline="white", width=2)
            sl_canvas.coords(sl_cursor["outer"], x - r - 1, y - r - 1, x + r + 1, y + r + 1)
            sl_canvas.coords(sl_cursor["inner"], x - r, y - r, x + r, y + r)

            hx = state["h"] * SQ
            if hue_cursor["line"] is None:
                hue_cursor["line"] = hue_canvas.create_line(0, 0, 0, HUE_H, fill="white", width=3)
            hue_canvas.coords(hue_cursor["line"], hx, 0, hx, HUE_H)

        def update_from_state(regen_square=False, sync_sliders=True):
            if regen_square:
                render_sl_square()
            redraw_cursors()
            r, g, b = colorsys.hls_to_rgb(state["h"], state["l"], state["s"])
            r, g, b = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            preview.config(bg=hex_color)
            hex_label.config(text=hex_color)
            chosen["rgb"] = (r, g, b)
            if sync_sliders:
                hue_var.set(state["h"] * 360)
                sat_var.set(state["s"] * 100)
                light_var.set(state["l"] * 100)

        def on_sl_pick(event):
            x = min(max(event.x, 0), SQ)
            y = min(max(event.y, 0), SQ)
            state["s"] = x / SQ
            state["l"] = 1 - y / SQ
            update_from_state()

        def on_hue_pick(event):
            x = min(max(event.x, 0), SQ)
            state["h"] = x / SQ
            update_from_state(regen_square=True)

        sl_canvas.bind("<Button-1>", on_sl_pick)
        sl_canvas.bind("<B1-Motion>", on_sl_pick)
        hue_canvas.bind("<Button-1>", on_hue_pick)
        hue_canvas.bind("<B1-Motion>", on_hue_pick)

        def on_slider_change(*_args):
            state["h"] = hue_var.get() / 360.0
            state["s"] = sat_var.get() / 100.0
            state["l"] = light_var.get() / 100.0
            update_from_state(regen_square=True, sync_sliders=False)

        def add_slider(row, label_text, var, to):
            ttk.Label(sliders_frame, text=label_text).grid(row=row, column=0, sticky="w")
            ttk.Scale(sliders_frame, from_=0, to=to, orient=tk.HORIZONTAL, variable=var,
                      command=on_slider_change).grid(row=row, column=1, sticky="ew", padx=10)

        add_slider(0, "Teinte", hue_var, 360)
        add_slider(1, "Saturation", sat_var, 100)
        add_slider(2, "Luminosité", light_var, 100)

        render_hue_bar()
        update_from_state(regen_square=True, sync_sliders=False)

        def pick_pixel_from(image, rect_attr):
            def handler(event):
                stop_picking()
                rect = getattr(self, rect_attr, None)
                if rect is None or image is None:
                    return
                x0, y0, ratio = rect
                if ratio <= 0:
                    return
                ix = int((event.x - x0) / ratio)
                iy = int((event.y - y0) / ratio)
                if 0 <= ix < image.width and 0 <= iy < image.height:
                    r, g, b = image.convert("RGB").getpixel((ix, iy))
                    state["h"], state["l"], state["s"] = colorsys.rgb_to_hls(
                        r / 255.0, g / 255.0, b / 255.0)
                    update_from_state(regen_square=True)
            return handler

        def stop_picking(*_args):
            self.original_canvas.config(cursor="")
            self.preview_canvas.config(cursor="")
            self.original_canvas.unbind("<Button-1>")
            self.preview_canvas.unbind("<Button-1>")
            self.root.unbind("<Escape>")
            dialog.grab_set()
            dialog.lift()
            dialog.focus_set()

        def start_picking():
            dialog.grab_release()
            self.original_canvas.config(cursor="crosshair")
            self.preview_canvas.config(cursor="crosshair")
            self.original_canvas.bind(
                "<Button-1>", pick_pixel_from(self.original_image, "_orig_display_rect"))
            self.preview_canvas.bind(
                "<Button-1>", pick_pixel_from(self.processed_image, "_preview_display_rect"))
            self.root.bind("<Escape>", stop_picking)
            self.root.lift()

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        ttk.Button(btn_frame, text="💧 Pipette", command=start_picking).pack(side=tk.LEFT)

        result = {"confirmed": False}

        def on_ok():
            stop_picking()
            result["confirmed"] = True
            dialog.destroy()

        def on_cancel():
            stop_picking()
            dialog.destroy()

        ttk.Button(btn_frame, text="Annuler", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        dialog.update_idletasks()
        dialog.grab_set()
        dialog.wait_window()

        return chosen["rgb"] if result["confirmed"] else None

    def _ensure_custom_palette(self):
        """Fige la palette actuelle en palette 'personnalisée' si ce n'est pas déjà le cas."""
        if self.custom_palette is None:
            base = self.current_palette if self.current_palette is not None \
                else np.array([[255, 255, 255]], dtype=np.uint8)
            self.custom_palette = np.array(base, dtype=np.uint8).copy()

    def edit_palette_color(self, index):
        """Ouvre le sélecteur de couleur système pour modifier une couleur de la palette."""
        if self.current_palette is None or index >= len(self.current_palette):
            return
        r, g, b = (int(v) for v in self.current_palette[index][:3])
        rgb = self.pick_color_hsl(initial_rgb=(r, g, b), title="Modifier la couleur")
        if rgb is None:
            return
        self._ensure_custom_palette()
        self.custom_palette[index] = [int(round(v)) for v in rgb]
        self.current_palette = self.custom_palette
        self.refresh_palette_display()
        self.on_any_change()

    def delete_palette_color(self, index):
        """Supprime une couleur de la palette (il doit en rester au moins une)."""
        if self.current_palette is None or index >= len(self.current_palette):
            return
        if len(self.current_palette) <= 1:
            messagebox.showwarning("Palette", "Il doit rester au moins une couleur dans la palette.")
            return
        self._ensure_custom_palette()
        self.custom_palette = np.delete(self.custom_palette, index, axis=0)
        self.current_palette = self.custom_palette
        self.refresh_palette_display()
        self.on_any_change()

    def add_palette_color(self):
        """Ajoute une nouvelle couleur choisie par l'utilisateur à la palette."""
        if not self.original_image:
            return
        rgb = self.pick_color_hsl(initial_rgb=(255, 255, 255), title="Ajouter une couleur")
        if rgb is None:
            return
        self._ensure_custom_palette()
        new_row = np.array([[int(round(v)) for v in rgb]], dtype=np.uint8)
        self.custom_palette = np.vstack([self.custom_palette, new_row])
        self.current_palette = self.custom_palette
        self.refresh_palette_display()
        self.on_any_change()

    def generate_auto_palette(self):
        """Abandonne la palette personnalisée et revient au calcul automatique (K-means)."""
        if not self.original_image:
            messagebox.showwarning("Avertissement", "Veuillez d'abord importer une image.")
            return
        self.custom_palette = None
        self.on_any_change()

    def reset(self):
        self.n_colors.set(16)
        self.keep_aspect.set(True)
        self.dither_var.set(False)
        if self.original_image:
            w, h = self.original_image.size
            self._aspect_ratio = w / h
            self._syncing_dims = True
            self.width_var.set(w)
            self.height_var.set(h)
            self._syncing_dims = False
        self.processed_image = None
        self.current_palette = None
        self.custom_palette = None
        self.resize_preview()
        self.refresh_palette_display()
        self.update_preview()

def main():
    root = tk.Tk()
    app = ColorReducerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()