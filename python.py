import subprocess
import sys
import time
from pathlib import Path
import platform
import socket
import argparse
import getpass
import json
import os

class VSCodeServerManager:
    def __init__(self):
        self.base_data_dir = Path.home() / ".vscode-servers"
        self.config_file = self.base_data_dir / "containers.json"
        self.base_image = "my-openvscode-server:latest"
        self.current_user = getpass.getuser()
        self.init_directories()

    def init_directories(self):
        self.base_data_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            self.save_containers_config({})

    def load_containers_config(self):
        if self.config_file.exists():
            return json.loads(self.config_file.read_text())
        return {}

    def save_containers_config(self, config):
        self.config_file.write_text(json.dumps(config, indent=2))

    def find_available_port(self, start_port=1024, max_port=65500):
        for port in range(start_port, max_port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('', port))
                    return port
                except socket.error:
                    continue
        raise RuntimeError("No available ports found")

    def create_base_image(self):
        try:
            result = subprocess.run(["docker", "images", "-q", self.base_image], 
                                 capture_output=True, text=True)
            if not result.stdout.strip():
                print("🏗️ Building base image...")
                dockerfile = """
FROM gitpod/openvscode-server:latest

USER root

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-tk \
    x11-apps \
    xvfb \
    libgl1-mesa-glx \
    nodejs \
    npm \
    curl \
    git

# Install Python packages
RUN pip3 install flask django streamlit tkinter pygame PyQt5

# Setup display for GUI
ENV DISPLAY=:0

# Configure workspace
RUN mkdir -p /home/workspace
WORKDIR /home/workspace

# Expose ports
EXPOSE 3000 8000 5000 3001 8501

CMD ["openvscode-server", "--without-connection-token", "--host", "0.0.0.0"]
"""
                dockerfile_path = self.base_data_dir / "Dockerfile"
                dockerfile_path.write_text(dockerfile)
                
                subprocess.run(
                    ["docker", "build", "-t", self.base_image, "-f", str(dockerfile_path), "."],
                    check=True
                )
                return True
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error creating base image: {e}")
            return False

    def create_container(self, name):
        try:
            config = self.load_containers_config()
            if name in config:
                print(f"❌ Container '{name}' already exists")
                return self.get_container_ports(name)

            ports = {
                "vscode": self.find_available_port(),
                "flask": self.find_available_port(),
                "django": self.find_available_port(),
                "react": self.find_available_port(),
                "streamlit": self.find_available_port()
            }

            data_dir = self.base_data_dir / name
            data_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                "docker", "run",
                "-d",
                "--init",
                "--name", f"vscode_{name}",
                "--hostname", name,
                "-e", "DISPLAY=:0",
                "-v", "/tmp/.X11-unix:/tmp/.X11-unix",
                "-v", f"{data_dir}:/home/workspace:cached",
                "--security-opt", "seccomp=unconfined"
            ]

            # Add port mappings
            for port in ports.values():
                cmd.extend(["-p", f"{port}:3000"])

            cmd.append(self.base_image)
            
            subprocess.run(cmd, check=True)
            
            config[name] = {
                "ports": ports,
                "data_dir": str(data_dir),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.save_containers_config(config)
            
            print(f"\n✅ Container '{name}' created successfully!")
            return ports

        except Exception as e:
            print(f"❌ Error creating container: {e}")
            return None

    def get_container_ports(self, name):
        config = self.load_containers_config()
        if name in config:
            return config[name]["ports"]
        return None

    def enable_gui_support(self, name):
        try:
            subprocess.run([
                "docker", "exec", f"vscode_{name}",
                "bash", "-c", "xhost + && export DISPLAY=:0"
            ], check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def list_containers(self):
        config = self.load_containers_config()
        if not config:
            print("No containers exist.")
            return

        print("\n📦 Existing containers:")
        for name, info in config.items():
            status = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=vscode_{name}"],
                capture_output=True, text=True
            )
            state = "🟢 Running" if status.stdout.strip() else "🔴 Stopped"
            print(f"\n• {name}")
            print(f"  - Status: {state}")
            print(f"  - Created: {info['created_at']}")
            print("  - Ports:")
            for service, port in info['ports'].items():
                print(f"    • {service}: http://localhost:{port}")

    def delete_container(self, name):
        config = self.load_containers_config()
        if name not in config:
            print(f"❌ Container '{name}' not found")
            return False

        try:
            subprocess.run(["docker", "stop", f"vscode_{name}"], capture_output=True)
            subprocess.run(["docker", "rm", f"vscode_{name}"], capture_output=True)
            del config[name]
            self.save_containers_config(config)
            print(f"✅ Container '{name}' deleted")
            return True
        except Exception as e:
            print(f"❌ Error during deletion: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='VSCode Server Manager')
    parser.add_argument('action', choices=['create', 'list', 'delete'],
                      help='Action to perform')
    parser.add_argument('name', nargs='?', help='Container name')

    args = parser.parse_args()
    manager = VSCodeServerManager()

    if not manager.create_base_image():
        sys.exit(1)

    if args.action == 'create' and args.name:
        manager.create_container(args.name)
    elif args.action == 'list':
        manager.list_containers()
    elif args.action == 'delete' and args.name:
        manager.delete_container(args.name)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
