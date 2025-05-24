import zipfile
import tempfile
from flask import Flask, render_template, request, send_file
import os
from authgraph.core.analyzer import analyze_project
from authgraph.exporter.csv_exporter import export_to_csv
from authgraph.core.neo4j_writer import push_to_neo4j

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.mkdtemp()

@app.route("/", methods=["GET", "POST"])
def index():
    routes = []
    if request.method == "POST":
        folder_files = request.files.getlist("folder")
        temp_dir = os.path.join(UPLOAD_FOLDER, "session")
        os.makedirs(temp_dir, exist_ok=True)

        for file in folder_files:
            path = os.path.join(temp_dir, file.filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            file.save(path)

        routes = analyze_project(temp_dir)
        export_to_csv(routes, os.path.join(UPLOAD_FOLDER, "permissions.csv"))
        push_to_neo4j(routes)

    return render_template("index.html", routes=routes)

@app.route("/download")
def download():
    return send_file(os.path.join(UPLOAD_FOLDER, "permissions.csv"), as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)