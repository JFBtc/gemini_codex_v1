# reset.py
import os
import glob

print("🧹 Nettoyage des données corrompues...")

# Chemin vers le dossier data
data_dir = os.path.join(os.getcwd(), "data")

if os.path.exists(data_dir):
    files = glob.glob(os.path.join(data_dir, "*.pkl"))
    if not files:
        print("✅ Aucun fichier à supprimer.")
    for f in files:
        try:
            os.remove(f)
            print(f"🗑️ Supprimé : {f}")
        except Exception as e:
            print(f"❌ Erreur : {e}")
else:
    print("✅ Dossier data introuvable (c'est propre).")

print("\n🚀 Vous pouvez relancer le programme !")
input("Appuyez sur Entrée pour quitter...")