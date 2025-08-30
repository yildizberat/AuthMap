# app_ai_authmap.py
import os
import io
import csv
import json
import time
import tempfile
from typing import List, Dict, Any

import requests
import pandas as pd
import gradio as gr

# ====== Ollama / Model Ayarları (ENV ile değiştirilebilir) ======
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "deepseek-r1:14b")  # örn: deepseek-coder-v2:lite
TEMPERATURE    = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
NUM_CTX        = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
MAX_RETRIES    = int(os.getenv("OLLAMA_RETRIES", "2"))
RETRY_WAIT_S   = float(os.getenv("OLLAMA_RETRY_WAIT", "1.0"))

# ====== Neo4j Ayarları (opsiyonel) ======
from py2neo import Graph
NEO4J_BOLT = os.getenv("NEO4J_BOLT", "bolt://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "test1234")

# ====== AI'ya verilecek katı prompt (parser şeması) ======
PROMPT = r"""
Return ONLY valid JSON. No prose, no code fences.

Goal: From the given Express.js/Node.js (or TS) code, extract HTTP routes and authorization info.
Output MUST follow the schema *exactly* and reflect real code (do not invent).

Schema:
{
  "routes": [
    {
      "file": "string",
      "line": 0,
      "source": "string",
      "method": "GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD|ALL",
      "path": "string (must start with /)",
      "roles": ["string"],
      "role": "string|null"
    }
  ]
}

Rules & Extraction Hints:
- Recognize simple calls: app.get('/x', ...), router.post('/y', ...).
- Recognize chained routing: router.route('/x').get(...).post(...).
- Recognize mounts: app.use('/base', routerVar) and resolve full path: full = base + subpath (normalize slashes).
- Detect roles from middlewares like checkRole('admin') or checkRole("user") within the call args; collect all roles.
- If multiple roles found, include them all in "roles" (deduped) and set "role" = first one.
- method MUST be uppercased. path MUST start with "/".
- file is the provided filename; line is approximate starting line for the route (best effort).
- If unknown/none, use [] for roles and null for role.
- Do not include duplicates. Do not output extra fields.

CODE (filename: <<<FILENAME>>>):
<<<CODE>>>
"""

# ======================= AI PARSER CORE =======================

def _ollama_call(endpoint: str, payload: dict) -> requests.Response:
    return requests.post(f"{OLLAMA_API_URL}{endpoint}", json=payload, timeout=180)

def _ollama_json(prompt: str) -> dict:
    """
    /api/generate -> JSON; 404 ise /api/chat fallback. Basit retry'lı.
    """
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # 1) generate
            r = _ollama_call("/api/generate", {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": TEMPERATURE, "num_ctx": NUM_CTX}
            })
            if r.status_code == 200:
                data = r.json().get("response", "")
                return json.loads(data)

            # 2) chat fallback sadece 404'te
            if r.status_code == 404:
                rc = _ollama_call("/api/chat", {
                    "model": OLLAMA_MODEL,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": TEMPERATURE, "num_ctx": NUM_CTX},
                    "messages": [
                        {"role": "system", "content": "Return ONLY valid JSON. No prose."},
                        {"role": "user", "content": prompt},
                    ]
                })
                if rc.status_code == 200:
                    data = rc.json()["message"]["content"]
                    return json.loads(data)
                last_err = RuntimeError(f"chat error {rc.status_code}: {rc.text}")
            else:
                last_err = RuntimeError(f"generate error {r.status_code}: {r.text}")
        except Exception as e:
            last_err = e

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_WAIT_S)
    raise last_err or RuntimeError("Ollama unknown error")

def _normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    file = rec.get("file") or "<memory>"
    try:
        line = int(rec.get("line") or 0)
    except Exception:
        line = 0
    source = rec.get("source") or "app"
    method = (rec.get("method") or "GET").upper().strip()
    path = (rec.get("path") or "").strip()
    if path and not path.startswith("/"):
        path = "/" + path

    roles = rec.get("roles") or []
    if not isinstance(roles, list):
        roles = [str(roles)]
    # dedupe
    seen = set()
    roles = [r for r in (str(x).strip() for x in roles) if r and (not (r in seen) and not seen.add(r))]
    role = rec.get("role") if rec.get("role") is not None else (roles[0] if roles else None)

    return {
        "file": file,
        "line": line,
        "source": source,
        "method": method,
        "path": path,
        "roles": roles,
        "role": role
    }

def parse_express_code_ai(js_code: str, filename: str = "<memory>") -> List[Dict]:
    prompt = PROMPT.replace("<<<CODE>>>", js_code).replace("<<<FILENAME>>>", filename)
    parsed = _ollama_json(prompt)
    items = parsed.get("routes", []) if isinstance(parsed, dict) else []
    return [_normalize_record(x) for x in items]

# ======================= CSV & NEO4J HELPERS =======================

def to_authmap_csv(records: List[Dict]) -> str:
    """
    AuthMap CSV şeması: path,method,roles,auth_type,description
    (auth_type/description şimdilik boş bırakılıyor; istersen prompt'a ekleyebiliriz)
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["path", "method", "roles", "auth_type", "description"])
    for r in records:
        roles_txt = ";".join(r.get("roles") or [])
        w.writerow([r["path"], r["method"], roles_txt, "", ""])
    return buf.getvalue()

def preview_df_from_records(records: List[Dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        rows.append({
            "path": r["path"],
            "method": r["method"],
            "roles": ";".join(r.get("roles") or [])
        })
    return pd.DataFrame(rows, columns=["path", "method", "roles"])

def push_to_neo4j(records: List[Dict]) -> str:
    graph = Graph(NEO4J_BOLT, auth=(NEO4J_USER, NEO4J_PASS))
    graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (r:Route) REQUIRE (r.path, r.method) IS NODE KEY;")
    graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (ro:Role) REQUIRE (ro.name) IS UNIQUE;")

    tx = graph.begin()
    for r in records:
        path = r["path"]
        method = r["method"]
        roles = r.get("roles") or []
        tx.run("MERGE (rt:Route {path:$path, method:$method})", path=path, method=method)
        for role in roles:
            tx.run("""
                MERGE (ro:Role {name:$role})
                MERGE (rt:Route {path:$path, method:$method})
                MERGE (rt)-[:REQUIRES_ROLE]->(ro)
            """, role=role, path=path, method=method)
    tx.commit()
    return f"Pushed {len(records)} routes to Neo4j @ {NEO4J_BOLT}"

# ======================= GRADIO UI =======================

def do_extract(code_text: str, filename_hint: str):
    if not code_text.strip():
        return "⚠️ Kod boş görünüyor.", pd.DataFrame(), None

    try:
        records = parse_express_code_ai(code_text, filename=filename_hint or "<memory>")
    except Exception as e:
        return f"❌ AI parse error: {e}", pd.DataFrame(), None

    # JSON görünüm
    json_view = json.dumps(records, ensure_ascii=False, indent=2)

    # DataFrame önizleme
    df = preview_df_from_records(records)

    # CSV dosyası oluştur (indirilebilir)
    csv_text = to_authmap_csv(records)
    fd, tmp_path = tempfile.mkstemp(prefix="authmap_", suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(csv_text)

    return json_view, df, tmp_path

def do_extract_and_push(code_text: str, filename_hint: str):
    json_view, df, csv_file = do_extract(code_text, filename_hint)
    # Eğer do_extract hata döndüyse json_view str içinde "error" olur.
    if isinstance(df, pd.DataFrame) and not df.empty and isinstance(json_view, str) and json_view.startswith("["):
        try:
            records = json.loads(json_view)
            msg = push_to_neo4j(records)
            json_view = json_view + f"\n\n# {msg}"
        except Exception as e:
            json_view = json_view + f"\n\n# Neo4j push ERROR: {e}"
    return json_view, df, csv_file

with gr.Blocks(title="AuthMap – AI Route/Auth Extractor") as demo:
    gr.Markdown("## 🔐 AuthMap – AI tabanlı Route/Authorization Parser\nKodunu yapıştır → AI ile AuthMap CSV üret → indir veya Neo4j’ye gönder.")

    with gr.Row():
        code_in = gr.Code(label="🧠 Server code (Express/Node/TS)", language="javascript", lines=20)
        file_hint = gr.Textbox(label="(Opsiyonel) Dosya adı/etiket", placeholder="server.js")

    with gr.Row():
        btn_extract = gr.Button("🧩 Extract CSV (AI)")
        btn_push = gr.Button("🚀 Extract & Push to Neo4j")

    gr.Markdown("### 📄 Kayıtlar (AI Parser çıktısı – regex parser şemanla birebir)")
    json_out = gr.Textbox(label="records[] (JSON)", lines=18)

    gr.Markdown("### 🛣️ AuthMap Routes Önizleme")
    df_out = gr.Dataframe(label="path / method / roles", wrap=True)

    gr.Markdown("### ⬇️ İndirilebilir CSV")
    file_out = gr.File(label="authmap.csv")

    btn_extract.click(do_extract, inputs=[code_in, file_hint], outputs=[json_out, df_out, file_out])
    btn_push.click(do_extract_and_push, inputs=[code_in, file_hint], outputs=[json_out, df_out, file_out])

demo.launch(share=False, server_name="127.0.0.1", server_port=7863)
