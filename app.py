#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
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
        
        # Variables pour les sliders
        self.n_colors = tk.IntVar(value=16)
        self.width_var = tk.IntVar(value=0)
        self.height_var = tk.IntVar(value=0)
        self.keep_aspect = tk.BooleanVar(value=True)
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
        
        # Frame des images (côte à côte)
        images_frame = ttk.Frame(main)
        images_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Original
        left_panel = ttk.LabelFrame(images_frame, text="Original", padding=5)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Canvas avec gestion du redimensionnement
        self.original_canvas = tk.Canvas(left_panel, bg="#2e2e2e", highlightthickness=0)
        self.original_canvas.pack(fill=tk.BOTH, expand=True)
        self.original_canvas.bind("<Configure>", lambda e: self.resize_original())
        
        # Résultat
        right_panel = ttk.LabelFrame(images_frame, text="Aperçu (PNG palettisé)", padding=5)
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
                  variable=self.n_colors, command=self.on_any_change).pack(
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
        
        # Boutons d'action
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="🔄 Réinitialiser", 
                   command=self.reset).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="💾 Exporter en PNG", 
                   command=self.export).pack(side=tk.RIGHT, padx=5)
        
        # Barre de progression / statut
        self.status = ttk.Label(main, text="Prêt", foreground="gray")
        self.status.pack(fill=tk.X, pady=(5, 0))
        
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

        if self.keep_aspect.get() and self._aspect_ratio:
            self._syncing_dims = True
            try:
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

                # Aperçu limité à 800px sur le plus grand côté, mais toujours
                # aux proportions exactes de la taille cible (pas de la source)
                max_preview = 800
                cap = min(1.0, max_preview / target_w, max_preview / target_h)
                preview_size = (max(1, round(target_w * cap)),
                                 max(1, round(target_h * cap)))

                result = process_image(self.original_image, n, size=preview_size)

                self.root.after(0, lambda: self.set_processed_image(result))
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
        
    def set_processed_image(self, pil_image):
        """Définit l'image traitée et la redimensionne."""
        self.processed_image = pil_image
        self.resize_preview()
        
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
        
        def task():
            try:
                n = self.n_colors.get()
                target_w = self.width_var.get()
                target_h = self.height_var.get()

                result = process_image(self.original_image, n, size=(target_w, target_h))
                result.save(path, "PNG", optimize=False)
                
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
                
        threading.Thread(target=task, daemon=True).start()
        
    def reset(self):
        self.n_colors.set(16)
        self.keep_aspect.set(True)
        if self.original_image:
            w, h = self.original_image.size
            self._aspect_ratio = w / h
            self._syncing_dims = True
            self.width_var.set(w)
            self.height_var.set(h)
            self._syncing_dims = False
        self.processed_image = None
        self.resize_preview()
        self.update_preview()

def main():
    root = tk.Tk()
    app = ColorReducerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()