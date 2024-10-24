import multiprocessing
import time
import python
import back
import json
from pathlib import Path
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

def run_python_server(container_name):
    manager = python.VSCodeServerManager()
    manager.create_base_image()
    ports = manager.create_container(container_name)
    print("\n🔌 Available ports:")
    for service, port in ports.items():
        print(f"- {service}: http://localhost:{port}")

def generate_file_content(file_path, prompt, context, container_name):
    workspace_path = back.get_container_workspace(container_name)
    relative_path = file_path.replace('workspace/', '', 1)
    full_path = workspace_path / relative_path
    
    if not file_path.endswith('/'):
        content = back.get_file_content_from_ai(
            file_path=file_path,
            prompt=prompt,
            context=context,
            model="claude-3.5-sonnet"
        )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        print(f"📝 Generated content for {file_path}")
        return content
    return None

def interactive_ai_session(container_name):
    context = back.load_context()
    history = FileHistory('.ai_prompt_history')
    
    print(f"\n🤖 AI Session started for container: {container_name}")
    print("Commands:")
    print("- Type your prompt to generate code")
    print("- 'ports' to show available ports")
    print("- 'gui' to enable GUI support")
    print("- 'exit' to quit\n")
    
    while True:
        user_input = prompt(
            '🤖 What would you like me to do? > ',
            history=history,
            auto_suggest=AutoSuggestFromHistory()
        )
        
        if user_input.lower() == 'exit':
            break
            
        if user_input.lower() == 'ports':
            manager = python.VSCodeServerManager()
            ports = manager.get_container_ports(container_name)
            print("\n🔌 Available ports:")
            for service, port in ports.items():
                print(f"- {service}: http://localhost:{port}")
            continue
            
        if user_input.lower() == 'gui':
            manager = python.VSCodeServerManager()
            manager.enable_gui_support(container_name)
            print("🖥️ GUI support enabled")
            continue
            
        # Get structure from AI
        existing_structure, file_contents = back.get_existing_structure(container_name)
        file_structure = back.get_file_structure_from_ai(
            prompt=user_input,
            context=json.dumps(context),
            existing_structure=existing_structure,
            file_contents=file_contents
        )
        
        print("\n🔨 Generating files and content...")
        
        # Generate content for each file
        new_contents = {}
        for file_path in file_structure.strip().split('\n'):
            if file_path.strip() and not file_path.endswith('/'):
                content = generate_file_content(
                    file_path=file_path,
                    prompt=user_input,
                    context=json.dumps(context),
                    container_name=container_name
                )
                if content:
                    new_contents[file_path] = content
        
        # Update context with new content
        context["files"] = new_contents
        back.save_context(context)
        
        print("\n✅ All files generated and populated!")

def main():
    container_name = input("Enter container name: ")
    
    print("🚀 Starting VSCode Server...")
    python_process = multiprocessing.Process(target=run_python_server, args=(container_name,))
    python_process.start()
    
    # Wait for container creation
    time.sleep(2)
    
    # Start interactive AI session
    interactive_ai_session(container_name)

if __name__ == '__main__':
    main()
