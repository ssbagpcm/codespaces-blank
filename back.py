import os
import requests
import re
import json
import shutil
from pathlib import Path
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

# API key
api_key = 'sk-RL49wKQm-0h4aS0s3xsYuCFWaCoOS4ryT5zgVSsvJs6R5rhz'

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

def get_container_workspace(container_name):
    base_config = Path.home() / ".vscode-servers" / "containers.json"
    if not base_config.exists():
        raise FileNotFoundError("Configuration des conteneurs non trouvée")
        
    with open(base_config) as f:
        config = json.load(f)
    
    if container_name not in config:
        raise ValueError(f"Conteneur {container_name} non trouvé")
        
    return Path(config[container_name]["data_dir"])

def get_existing_structure(container_name):
    workspace_path = get_container_workspace(container_name)
    structure = []
    file_contents = {}
    
    for root, dirs, files in os.walk(workspace_path):
        for name in files:
            file_path = os.path.relpath(os.path.join(root, name), workspace_path)
            structure.append(file_path)
            try:
                with open(os.path.join(root, name), 'r', encoding='utf-8') as f:
                    file_contents[file_path] = f.read()
            except Exception as e:
                print(f"Erreur lecture fichier {file_path}: {e}")
        for name in dirs:
            structure.append(os.path.relpath(os.path.join(root, name), workspace_path) + '/')
    return '\n'.join(sorted(structure)), file_contents

def get_file_structure_from_ai(prompt, context, existing_structure, file_contents, model="claude-3.5-sonnet", max_tokens=100000):
    base_prompt = """You are a Python expert who must follow these rules STRICTLY and WITHOUT EXCEPTION:

1. ALL files MUST be inside a 'workspace' folder
2. NEVER create Git, LICENSE, or config files
3. Create ONLY essential files - if one file works, don't make more
4. ALWAYS include a readme.md with clear code documentation
5. ONLY explain code in readme.md, no credits or metadata
6. NO code blocks in readme.md
7. ALL files must be executable and follow best practices
8. NEVER create virtual environments or dependency files
9. ALL paths must start with 'workspace/'
10. ONLY respond with file paths, one per line

Example valid response:
workspace/main.py
workspace/readme.md

Example invalid response:
src/main.py
.gitignore
requirements.txt"""

    project_prompt = f"""Current project request: {prompt}

Existing structure:
{existing_structure}

Existing files content:
{json.dumps(file_contents, indent=2)}

Project context: {context}

Remember: ONLY respond with valid file paths, one per line."""

    messages = [
        {"role": "system", "content": base_prompt},
        {"role": "user", "content": project_prompt}
    ]

    response = requests.post("https://cablyai.com/v1/chat/completions", 
                           headers=headers, 
                           json={"model": model, "messages": messages, "max_tokens": max_tokens})
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    
    return "workspace/main.py\nworkspace/readme.md"

def get_file_content_from_ai(file_path, prompt, context, existing_content="", existing_structure="", file_contents={}, model="claude-3.5-sonnet", max_tokens=4000):
    ext = file_path.split('.')[-1].lower() if '.' in file_path else 'txt'
    
    file_type_prompt = f"""Generate ONLY the content for this specific file: {file_path}
Based on the request: {prompt}

STRICT RULES:
1. Generate ONLY the file content, no explanations or comments
2. Content must be complete and functional
3. Content must be appropriate for .{ext} file type
4. Follow proper formatting and indentation
5. No markdown formatting or code blocks
6. No mixing of different file types

Context: {context}
Current structure: {existing_structure}
Other files: {json.dumps(file_contents, indent=2)}"""

    messages = [
        {"role": "system", "content": "You are a file content generation expert. Generate only the actual file content, nothing else."},
        {"role": "user", "content": file_type_prompt}
    ]
    
    response = requests.post("https://cablyai.com/v1/chat/completions", 
                           headers=headers, 
                           json={"model": model, "messages": messages, "max_tokens": max_tokens})
    
    if response.status_code == 200:
        content = response.json()['choices'][0]['message']['content']
        return clean_markdown(content)
    else:
        return f"Error: {response.status_code}"

def clean_markdown(content):
    def preserve_indentation(line):
        return re.match(r'^(\s*)', line).group(1)

    lines = content.split('\n')
    cleaned_lines = []
    in_code_block = False
    
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
            
        if not in_code_block:
            line = re.sub(r'`([^`]+)`', r'\1', line)
            indent = preserve_indentation(line)
            cleaned_line = indent + line.strip()
            
            if cleaned_line.strip():
                cleaned_lines.append(cleaned_line)
        else:
            if line.strip():
                cleaned_lines.append(line)

    cleaned_content = '\n'.join(cleaned_lines)
    return re.sub(r'\n\s*\n', '\n\n', cleaned_content).strip()

def move_unused_files_to_bin(structure_text, workspace_path):
    new_files = set(line.strip() for line in structure_text.strip().split('\n') if line.strip())
    existing_files = set()
    
    for root, dirs, files in os.walk(workspace_path):
        for file in files:
            path = os.path.relpath(os.path.join(root, file), workspace_path)
            existing_files.add(path)
    
    unused_files = existing_files - new_files
    bin_path = workspace_path / "deleted_files"
    bin_path.mkdir(exist_ok=True)
    
    for file in unused_files:
        if not str(file).startswith(str(bin_path)):
            source = workspace_path / file
            destination = bin_path / os.path.basename(file)
            shutil.move(str(source), str(destination))
            print(f"Fichier déplacé vers bin : {file}")

def remove_empty_directories(workspace_path):
    for root, dirs, files in os.walk(workspace_path, topdown=False):
        for dir in dirs:
            dir_path = Path(root) / dir
            if not any(dir_path.iterdir()) and dir != "deleted_files":
                dir_path.rmdir()
                print(f"Dossier vide supprimé : {dir_path}")

def create_or_update_files(structure_text, prompt, context, container_name):
    workspace_path = get_container_workspace(container_name)
    lines = structure_text.strip().split('\n')
    
    move_unused_files_to_bin(structure_text, workspace_path)
    existing_structure, file_contents = get_existing_structure(container_name)
    
    for line in lines:
        path = line.strip()
        if not path:
            continue
        
        relative_path = path.replace('workspace/', '', 1)
        full_path = workspace_path / relative_path
        
        if path.endswith('/'):
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"Dossier créé ou mis à jour : {full_path}")
        else:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            existing_content = file_contents.get(relative_path, "")
            
            content = get_file_content_from_ai(path, prompt, context, existing_content, existing_structure, file_contents)
            
            full_path.write_text(content, encoding='utf-8')
            print(f"Fichier créé ou mis à jour : {full_path}")

    remove_empty_directories(workspace_path)
    print(f"Structure de fichiers générée dans le conteneur '{container_name}'")

def load_context():
    context_file = Path("workspace_context.json")
    if context_file.exists():
        return json.loads(context_file.read_text(encoding='utf-8'))
    return {"prompts": [], "files": {}}

def save_context(context):
    Path("workspace_context.json").write_text(json.dumps(context, indent=2), encoding='utf-8')

def update_context(context, prompt, file_structure, container_name):
    workspace_path = get_container_workspace(container_name)
    context["prompts"].append(prompt)
    context["files"] = {}
    
    for line in file_structure.strip().split('\n'):
        path = line.strip()
        if path and not path.endswith('/'):
            relative_path = path.replace('workspace/', '', 1)
            full_path = workspace_path / relative_path
            if full_path.exists():
                context["files"][path] = full_path.read_text(encoding='utf-8')
    save_context(context)

def generate_workspace_from_prompt(prompt, context, container_name):
    existing_structure, file_contents = get_existing_structure(container_name)
    file_structure = get_file_structure_from_ai(prompt, json.dumps(context), existing_structure, file_contents)
    print("Structure générée ou mise à jour par l'IA :\n", file_structure)
    
    create_or_update_files(file_structure, prompt, json.dumps(context), container_name)
    update_context(context, prompt, file_structure, container_name)

def main():
    context = load_context()
    history = FileHistory('.prompt_history')
    
    container_name = input("Entrez le nom du conteneur VSCode : ")
    
    while True:
        user_prompt = prompt('Entrez votre prompt (ou "q" pour quitter) : ',
                             history=history,
                             auto_suggest=AutoSuggestFromHistory())
        
        if user_prompt.lower() == 'q':
            break
        
        generate_workspace_from_prompt(user_prompt, context, container_name)

if __name__ == "__main__":
    main()
