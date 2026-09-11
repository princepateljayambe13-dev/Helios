import os

# Folders and files to completely ignore
IGNORE_DIRS = {'node_modules', 'venv', '.venv', 'env', '__pycache__', '.git', 'dist', 'build'}
IGNORE_FILES = {'.env', '.DS_Store', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'}
# Only include these readable code extensions
VALID_EXTENSIONS = {'.js', '.ts', '.py', '.go', '.json', '.java', '.rb', '.php', '.sql'}

def bundle_backend(root_dir, output_file):
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# Backend Codebase Bundle\n\n")
        
        for root, dirs, files in os.walk(root_dir):
            # Filter out ignored directories in place
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                    
                ext = os.path.splitext(file)[1].lower()
                if ext in VALID_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, root_dir)
                    
                    outfile.write(f"## File: {rel_path}\n")
                    outfile.write(f"```{ext.strip('.')}\n")
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as infile:
                            outfile.write(infile.read())
                    except Exception as e:
                        outfile.write(f"// Error reading file: {str(e)}\n")
                    outfile.write("\n```\n\n")

bundle_backend('.', 'backend_bundle.md')
print("Bundle created as backend_bundle.md")

