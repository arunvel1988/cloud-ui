import os
import shutil
import subprocess
from flask import Flask, render_template
from flask import request
import string
from flask import request, render_template, redirect, url_for
import docker


client = docker.from_env()


import random
app = Flask(__name__)

def get_os_family():
    if os.path.exists("/etc/debian_version"):
        return "debian"
    elif os.path.exists("/etc/redhat-release"):
        return "redhat"
    else:
        return "unknown"




def install_package(tool, os_family):
    package_map = {
        "docker": "docker.io" if os_family == "debian" else "docker",
        "pip3": "python3-pip",
        "python3-venv": "python3-venv",
        "docker-compose": None  # We'll handle it manually
    }

    package_name = package_map.get(tool, tool)

    try:
        if os_family == "debian":
            subprocess.run(["sudo", "apt", "update"], check=True)

            if tool == "terraform":
                subprocess.run(["sudo", "apt", "install", "-y", "wget", "gnupg", "software-properties-common", "curl"], check=True)
                subprocess.run([
                    "wget", "-O", "hashicorp.gpg", "https://apt.releases.hashicorp.com/gpg"
                ], check=True)
                subprocess.run([
                    "gpg", "--dearmor", "--output", "hashicorp-archive-keyring.gpg", "hashicorp.gpg"
                ], check=True)
                subprocess.run([
                    "sudo", "mv", "hashicorp-archive-keyring.gpg", "/usr/share/keyrings/hashicorp-archive-keyring.gpg"
                ], check=True)

                codename = subprocess.check_output(["lsb_release", "-cs"], text=True).strip()
                apt_line = (
                    f"deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] "
                    f"https://apt.releases.hashicorp.com {codename} main\n"
                )
                with open("hashicorp.list", "w") as f:
                    f.write(apt_line)
                subprocess.run(["sudo", "mv", "hashicorp.list", "/etc/apt/sources.list.d/hashicorp.list"], check=True)

                subprocess.run(["sudo", "apt", "update"], check=True)
                subprocess.run(["sudo", "apt", "install", "-y", "terraform"], check=True)

            elif tool == "docker-compose":
                subprocess.run(["sudo", "apt", "install", "-y", "docker-compose"], check=True)

            else:
                subprocess.run(["sudo", "apt", "install", "-y", package_name], check=True)

        elif os_family == "redhat":
            if tool == "terraform":
                subprocess.run(["sudo", "yum", "install", "-y", "yum-utils"], check=True)
                subprocess.run([
                    "sudo", "yum-config-manager", "--add-repo",
                    "https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo"
                ], check=True)
                subprocess.run(["sudo", "yum", "install", "-y", "terraform"], check=True)

            elif tool == "docker-compose":
                subprocess.run(["sudo", "yum", "install", "-y", "docker-compose"], check=True)

            else:
                subprocess.run(["sudo", "yum", "install", "-y", package_name], check=True)

        else:
            return False, "Unsupported OS"

        return True, None

    except Exception as e:
        return False, str(e)




@app.route("/pre-req")
def prereq():
    tools = ["pip3", "openssl", "docker", "terraform","docker-compose"]
    results = {}
    os_family = get_os_family()

    for tool in tools:
        if shutil.which(tool):
            results[tool] = "✅ Installed"
        else:
            success, error = install_package(tool, os_family)
            if success:
                results[tool] = "❌ Not Found → 🛠️ Installed"
            else:
                results[tool] = f"❌ Not Found → ❌ Error: {error}"



    docker_installed = shutil.which("docker") is not None
    return render_template("prereq.html", results=results, os_family=os_family, docker_installed=docker_installed)












# Check if Portainer is actually installed and running (or exists as a container)
def is_portainer_installed():
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "portainer"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.strip() in ["true", "false"]
    except Exception:
        return False

# Actually run Portainer
def run_portainer():
    try:
        subprocess.run(["docker", "volume", "create", "portainer_data"], check=True)
        subprocess.run([
            "docker", "run", "-d",
            "-p", "9443:9443", "-p", "9000:9000",
            "--name", "portainer",
            "--restart=always",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", "portainer_data:/data",
            "portainer/portainer-ce:latest"
        ], check=True)
        return True, "✅ Portainer installed successfully."
    except subprocess.CalledProcessError as e:
        return False, f"❌ Docker Error: {str(e)}"

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/install_portainer", methods=["GET", "POST"])
def install_portainer_route():
    installed = is_portainer_installed()
    portainer_url = "https://localhost:9443"
    message = None

    if request.method == "POST":
        if not installed:
            success, message = run_portainer()
            installed = success
        else:
            message = "ℹ️ Portainer is already installed."

    return render_template("portainer.html", installed=installed, message=message, url=portainer_url)






#############################################################################################################

@app.route("/cloud/aws")
def cloud_aws():
    return render_template("aws.html")

@app.route("/cloud/azure")
def cloud_azure():
    return render_template("azure.html")

@app.route("/cloud/gcp")
def cloud_gcp():
    return render_template("gcp.html")

@app.route("/cloud/oci")
def cloud_oci():
    return render_template("oci.html")

import subprocess
from flask import render_template_string

@app.route("/launch_container/<provider>")
def launch_container(provider):
    """
    Launches or reuses a Docker container with all CLIs installed.
    """
    container_name = f"{provider}_cli_lab"
    image_name = "arunvel1988/cloud-shell"

    try:
        # Check if container exists
        check_cmd = ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"]
        existing = subprocess.check_output(check_cmd, text=True).strip()

        if existing == container_name:
            # Check if running
            running_cmd = ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"]
            running = subprocess.check_output(running_cmd, text=True).strip()

            if running == container_name:
                message = f"✅ {provider.upper()} CLI container is already running!<br>Use: <code>docker exec -it {container_name} /bin/bash</code>"
            else:
                # Start the stopped container
                subprocess.run(["docker", "start", container_name], check=True)
                message = f"▶️ Restarted existing {provider.upper()} CLI container.<br>Use: <code>docker exec -it {container_name} /bin/bash</code>"
        else:
            # Run new container
            cmd = [
                "docker", "run", "-dit",
                "--name", container_name,
                image_name,
                "/bin/bash"
            ]
            subprocess.run(cmd, check=True)
            message = f"🚀 New {provider.upper()} CLI container launched successfully!<br>Use: <code>docker exec -it {container_name} /bin/bash</code>"

    except subprocess.CalledProcessError as e:
        message = f"❌ Failed to launch container: {str(e)}"

    # Return styled HTML with back buttons
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>{provider.upper()} CLI Launch</title>
      <style>
        body {{
          font-family: 'Segoe UI', sans-serif;
          background: linear-gradient(135deg, #f1f8e9, #e3f2fd);
          padding: 50px;
          text-align: center;
          color: #333;
        }}
        .box {{
          background: #fff;
          padding: 30px;
          border-radius: 15px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.1);
          display: inline-block;
          max-width: 700px;
        }}
        h1 {{ color: #1565c0; }}
        .btn {{
          display: inline-block;
          margin: 15px;
          padding: 12px 25px;
          background: linear-gradient(to right, #42a5f5, #1565c0);
          color: #fff;
          text-decoration: none;
          border-radius: 10px;
          transition: 0.3s;
        }}
        .btn:hover {{ background: linear-gradient(to right, #1565c0, #0d47a1); }}
      </style>
    </head>
    <body>
      <div class="box">
        <h1>CLI Container Status</h1>
        <p>{message}</p>
        <a class="btn" href="/cloud">⬅ Back to Cloud Overview</a>
        <a class="btn" href="/">🏠 Back to Home</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(html)



##################ANSIBLE INSTALLATION##################

@app.route("/cloud")
def db_info():
    return render_template("cloud_info.html")





if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6002, debug=True)
