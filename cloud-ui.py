import os
import shutil
import subprocess
from flask import Flask, render_template
from flask import request
import string
from flask import request, render_template,render_template_string, redirect, url_for, flash
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

############################### launch + auth ############################################################


app.secret_key = "supersecret"

UPLOAD_FOLDER = "/tmp"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


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

    # HTML response
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
        <a class="btn" href="/cloud/{provider}/auth">Cloud Authentication</a>
        <a class="btn" href="/">🏠 Back to Home</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(html)


@app.route("/cloud/<provider>/auth", methods=["GET", "POST"])
def cloud_auth(provider):
    """
    Dynamic authentication page per cloud provider
    """

    if request.method == "POST":
        if provider == "gcp":
            file = request.files["file"]
            if file and file.filename.endswith(".json"):
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], "key.json")
                file.save(filepath)
                container = "gcp_cli_lab"
                try:
                    subprocess.run(
                        ["docker", "cp", filepath, f"{container}:/root/key.json"],
                        check=True
                    )
                    subprocess.run(
                        ["docker", "exec", container, "gcloud", "auth",
                         "activate-service-account", "--key-file", "/root/key.json"],
                        check=True
                    )
                    flash("✅ GCP Auth Successful with Service Account!")
                except subprocess.CalledProcessError as e:
                    flash(f"❌ Error: {e}")

        elif provider == "aws":
            access_key = request.form.get("access_key")
            secret_key = request.form.get("secret_key")
            region = request.form.get("region", "us-east-1")
            container = "aws_cli_lab"
            try:
                subprocess.run(
                    ["docker", "exec", container, "aws", "configure", "set",
                     "aws_access_key_id", access_key], check=True
                )
                subprocess.run(
                    ["docker", "exec", container, "aws", "configure", "set",
                     "aws_secret_access_key", secret_key], check=True
                )
                subprocess.run(
                    ["docker", "exec", container, "aws", "configure", "set",
                     "region", region], check=True
                )
                flash("✅ AWS Auth Successful!")
            except subprocess.CalledProcessError as e:
                flash(f"❌ Error: {e}")

        elif provider == "azure":
            client_id = request.form.get("client_id")
            tenant_id = request.form.get("tenant_id")
            secret = request.form.get("client_secret")
            subscription = request.form.get("subscription_id")
            container = "azure_cli_lab"
            try:
                subprocess.run(
                    ["docker", "exec", container, "az", "login",
                     "--service-principal",
                     "-u", client_id, "-p", secret, "--tenant", tenant_id],
                    check=True
                )
                subprocess.run(
                    ["docker", "exec", container, "az", "account", "set",
                     "--subscription", subscription],
                    check=True
                )
                flash("✅ Azure Auth Successful!")
            except subprocess.CalledProcessError as e:
                flash(f"❌ Error: {e}")

        elif provider == "oci":
            file = request.files["file"]
            if file:
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], "oci_config")
                file.save(filepath)
                container = "oci_cli_lab"
                try:
                    subprocess.run(
                        ["docker", "cp", filepath, f"{container}:/root/.oci/config"],
                        check=True
                    )
                    flash("✅ OCI Config uploaded successfully!")
                except subprocess.CalledProcessError as e:
                    flash(f"❌ Error: {e}")

        return redirect(url_for("cloud_auth", provider=provider))

    # ----------- Fancy HTML Styling ----------- #
    base_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>{provider_name} Authentication</title>
      <style>
        body {{
          font-family: 'Segoe UI', sans-serif;
          background: linear-gradient(135deg, #f3e5f5, #e1f5fe);
          display: flex;
          justify-content: center;
          align-items: center;
          height: 100vh;
          margin: 0;
        }}
        .card {{
          background: #fff;
          padding: 30px;
          border-radius: 20px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.15);
          width: 400px;
          text-align: center;
        }}
        h2 {{
          color: #1565c0;
          margin-bottom: 20px;
        }}
        input {{
          width: 90%;
          padding: 12px;
          margin: 8px 0;
          border: 1px solid #ccc;
          border-radius: 10px;
        }}
        button {{
          background: linear-gradient(to right, #42a5f5, #1565c0);
          color: white;
          border: none;
          padding: 12px 20px;
          margin-top: 15px;
          border-radius: 10px;
          cursor: pointer;
          transition: 0.3s;
          width: 100%;
        }}
        button:hover {{
          background: linear-gradient(to right, #1565c0, #0d47a1);
        }}
        a {{
          display: inline-block;
          margin-top: 15px;
          text-decoration: none;
          color: #1565c0;
          font-weight: bold;
        }}
      </style>
    </head>
    <body>
      <div class="card">
        {form_html}
        <a href="/cloud">⬅ Back to Cloud Overview</a><br>
        <a href="/">🏠 Home</a>
      </div>
    </body>
    </html>
    """

    if provider == "gcp":
        form_html = """
        <h2>☁️ Upload GCP Key JSON</h2>
        <form method="POST" enctype="multipart/form-data">
          <input type="file" name="file" accept=".json" required>
          <button type="submit">Upload & Authenticate</button>
        </form>
        """
    elif provider == "aws":
        form_html = """
        <h2>☁️ AWS Credentials</h2>
        <form method="POST">
          <input type="text" name="access_key" placeholder="Access Key" required>
          <input type="password" name="secret_key" placeholder="Secret Key" required>
          <input type="text" name="region" value="us-east-1" placeholder="Region">
          <button type="submit">Save & Authenticate</button>
        </form>
        """
    elif provider == "azure":
        form_html = """
        <h2>🔷 Azure Service Principal</h2>
        <form method="POST">
          <input type="text" name="client_id" placeholder="Client ID" required>
          <input type="text" name="tenant_id" placeholder="Tenant ID" required>
          <input type="password" name="client_secret" placeholder="Client Secret" required>
          <input type="text" name="subscription_id" placeholder="Subscription ID" required>
          <button type="submit">Login</button>
        </form>
        """
    elif provider == "oci":
        form_html = """
        <h2>🔴 Upload OCI Config</h2>
        <form method="POST" enctype="multipart/form-data">
          <input type="file" name="file" required>
          <button type="submit">Upload Config</button>
        </form>
        """
    else:
        form_html = "<p>❌ Unsupported provider</p>"

    return render_template_string(base_template.format(
        provider_name=provider.upper(),
        form_html=form_html
    ))




##################ANSIBLE INSTALLATION##################

@app.route("/cloud")
def db_info():
    return render_template("cloud_info.html")





if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6002, debug=True)
