#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
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
        
        self.input_path = None
        self.original_image = None
        self.processed_image = None  # Image traitée (PIL)
        self.current_palette = None  # Palette (N, 3) de la dernière image traitée
        self.custom_palette = None  # Si défini, palette éditée à la main (remplace le calcul K-means)
        self.export_progress = tk.DoubleVar(value=0)

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

                # Aperçu limité à 800px sur le plus grand côté (300px si dithering,
                # car la diffusion d'erreur est bien plus lente), mais toujours
                # aux proportions exactes de la taille cible (pas de la source)
                max_preview = 300 if dither else 800
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
        """Dialogue modal de sélection de couleur par Teinte/Saturation/Luminosité.
        Retourne un tuple (r, g, b) en 0-255, ou None si annulé."""
        r0, g0, b0 = (v / 255.0 for v in initial_rgb)
        h0, l0, s0 = colorsys.rgb_to_hls(r0, g0, b0)

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        hue_var = tk.DoubleVar(value=h0 * 360)
        sat_var = tk.DoubleVar(value=s0 * 100)
        light_var = tk.DoubleVar(value=l0 * 100)
        chosen = {"rgb": tuple(initial_rgb)}

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(2, weight=1)

        preview = tk.Frame(frame, width=70, height=70, relief="solid", borderwidth=1)
        preview.grid(row=0, column=0, rowspan=3, padx=(0, 15))
        preview.grid_propagate(False)

        hex_label = ttk.Label(frame, text="", font=("Courier", 10))
        hex_label.grid(row=3, column=0, pady=(8, 0))

        def update_preview(*_args):
            h = hue_var.get() / 360.0
            s = sat_var.get() / 100.0
            l = light_var.get() / 100.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            r, g, b = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            preview.config(bg=hex_color)
            hex_label.config(text=hex_color)
            chosen["rgb"] = (r, g, b)

        def add_slider(row, label_text, var, to):
            ttk.Label(frame, text=label_text).grid(row=row, column=1, sticky="w")
            ttk.Scale(frame, from_=0, to=to, orient=tk.HORIZONTAL, variable=var,
                      command=update_preview).grid(row=row, column=2, sticky="ew", padx=10)

        add_slider(0, "Teinte", hue_var, 360)
        add_slider(1, "Saturation", sat_var, 100)
        add_slider(2, "Luminosité", light_var, 100)
        update_preview()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(15, 0), sticky="e")

        result = {"confirmed": False}

        def on_ok():
            result["confirmed"] = True
            dialog.destroy()

        def on_cancel():
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