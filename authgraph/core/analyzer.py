from authgraph.scanner.file_scanner import find_js_files
from authgraph.scanner.express_parser import parse_express_code

def analyze_project(path):
    all_routes = []
    for file in find_js_files(path):
        try:
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()
            all_routes.extend(parse_express_code(content, filename=file))
        except Exception as e:
            # İstersen logla
            pass
    return all_routes
