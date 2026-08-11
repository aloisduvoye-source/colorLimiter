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
        self.scale_percent = tk.IntVar(value=100)
        self.keep_aspect = tk.BooleanVar(value=True)
        
        self.setup_ui()
        self.bind_events()
        
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
        
        # Slider couleurs
        color_frame = ttk.Frame(controls)
        color_frame.pack(fill=tk.X, pady=2)
        ttk.Label(color_frame, text="Couleurs :").pack(side=tk.LEFT)
        ttk.Scale(color_frame, from_=2, to=256, orient=tk.HORIZONTAL,
                  variable=self.n_colors, command=self.on_any_change).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.color_label = ttk.Label(color_frame, text="16")
        self.color_label.pack(side=tk.RIGHT)
        
        # Slider échelle
        scale_frame = ttk.Frame(controls)
        scale_frame.pack(fill=tk.X, pady=2)
        ttk.Label(scale_frame, text="Échelle :").pack(side=tk.LEFT)
        ttk.Scale(scale_frame, from_=10, to=200, orient=tk.HORIZONTAL,
                  variable=self.scale_percent, command=self.on_any_change).pack(
                      side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.scale_label = ttk.Label(scale_frame, text="100 %")
        self.scale_label.pack(side=tk.RIGHT)
        
        # Options
        opt_frame = ttk.Frame(controls)
        opt_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(opt_frame, text="Conserver les proportions",
                        variable=self.keep_aspect).pack(side=tk.LEFT)
        
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
        
    def bind_events(self):
        self.n_colors.trace_add("write", self.update_labels)
        self.scale_percent.trace_add("write", self.update_labels)
        
    def update_labels(self, *args):
        self.color_label.config(text=str(self.n_colors.get()))
        self.scale_label.config(text=f"{self.scale_percent.get()} %")
        
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
                scale = self.scale_percent.get() / 100.0
                
                # On travaille sur une copie pour l'aperçu
                # On limite la taille pour l'aperçu (max 800px)
                preview = self.original_image.copy()
                preview.thumbnail((800, 800), Image.Resampling.LANCZOS)
                
                # Applique le scale sur l'aperçu
                if scale != 1.0:
                    w, h = preview.size
                    preview = preview.resize((int(w*scale), int(h*scale)), 
                                             Image.Resampling.LANCZOS)
                
                result = process_image(preview, n, scale=1.0)  # déjà redimensionné
                
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
                scale = self.scale_percent.get() / 100.0
                
                result = process_image(self.original_image, n, scale=scale)
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
        self.scale_percent.set(100)
        self.keep_aspect.set(True)
        self.processed_image = None
        self.resize_preview()
        self.update_preview()

def main():
    root = tk.Tk()
    app = ColorReducerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()