import tkinter as tk
from tkinter import filedialog
import shutil
import os

def zip_selected_folder():
    root = tk.Tk()
    root.withdraw()

    folder_path = filedialog.askdirectory(title="Select Folder to Zip")
    
    if not folder_path:
        print("No folder selected. Exiting.")
        return

    parent_dir = os.path.dirname(folder_path)
    folder_name = os.path.basename(folder_path)
    
    output_path = os.path.join(parent_dir, folder_name)

    print(f"Zipping: {folder_path}...")
    shutil.make_archive(output_path, 'zip', folder_path)
    
    print(f"Success! Created: {output_path}.zip")

if __name__ == "__main__":
    zip_selected_folder()
