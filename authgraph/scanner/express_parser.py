import re


def parse_express_code(js_code):
    route_pattern = re.compile(r'app\.(get|post|put|delete)\(["\'](.*?)["\'].*?checkRole\(["\'](.*?)["\']\)', re.DOTALL)
    matches = route_pattern.findall(js_code)
    results = []
    for method, path, role in matches:
        results.append({
            "method": method.upper(),
            "path": path,
            "role": role
        })
    return results

# --- accessmap/core/analyzer.py ---
from authgraph.scanner.file_scanner import find_js_files
from authgraph.scanner.express_parser import parse_express_code

def analyze_project(path):
    all_routes = []
    for file in find_js_files(path):
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
            all_routes.extend(parse_express_code(content))
    return all_routes