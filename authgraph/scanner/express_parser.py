
import re
from typing import List, Dict, Tuple

METHODS = ("get", "post", "put", "delete", "patch", "options", "all")

# --- Yardımcı regex'ler ---
RE_APP_VARS = re.compile(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*express\s*\(\s*\)', re.MULTILINE)
RE_ROUTER_VARS = re.compile(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*express\.Router\s*\(\s*\)', re.MULTILINE)

# app.use('/base', routerVar) eşleşmeleri
RE_MOUNTS = re.compile(
    r'([A-Za-z_$][\w$]*)\.use\(\s*(?P<q>["\'])(?P<base>.*?)\1\s*,\s*([A-Za-z_$][\w$]*)\s*\)',
    re.DOTALL
)

# router.route('/x').get(...).post(...)
RE_ROUTE_CHAIN = re.compile(
    r'(?P<obj>[A-Za-z_$][\w$]*)\.route\(\s*(?P<path>(?P<q1>["\'])(?P<spath>.*?)(?P=q1)|`(?P<tpath>[^`]+)`)\s*\)\s*(?P<chain>(?:\.(?:get|post|put|delete|patch|options|all)\s*$begin:math:text$.*?$end:math:text$)+)',
    re.DOTALL
)

# Basit method çağrısı: app.get("/x", ...)
RE_SIMPLE_CALL_HEAD = re.compile(
    r'(?P<obj>[A-Za-z_$][\w$]*)\.(?P<method>get|post|put|delete|patch|options|all)\s*\(',
    re.DOTALL
)

# Argüman içinden path’i çekmek için (1. argüman string ya da template literal)
RE_FIRST_ARG_PATH = re.compile(
    r'^\s*(?:(?P<q>["\'])(?P<spath>.*?)(?P=q)|`(?P<tpath>[^`]+)`)',
    re.DOTALL
)

# Argüman içinden rolleri çekmek için
RE_CHECK_ROLE = re.compile(r'checkRole\s*\(\s*(?P<q>["\'])(?P<role>.*?)\1\s*\)', re.DOTALL)

def _find_var_names(pattern: re.Pattern, code: str) -> List[str]:
    return list({m.group(1) for m in pattern.finditer(code)})

def _find_mounts(code: str) -> List[Tuple[str, str, str]]:
    """
    appVar.use('/base', routerVar) -> (appVar, '/base', routerVar)
    """
    mounts = []
    for m in RE_MOUNTS.finditer(code):
        app_var = m.group(1)
        base = m.group('base') or ""
        after = code[m.end():]
        full = m.group(0)
        tail_id = re.findall(r',\s*([A-Za-z_$][\w$]*)\s*\)', full)
        router_var = tail_id[-1] if tail_id else ''
        mounts.append((app_var, base, router_var))
    return mounts

def _combine_paths(base: str, path: str) -> str:
    if not base:
        return path
    if not path:
        return base
    if base.endswith('/') and path.startswith('/'):
        return base.rstrip('/') + path
    if not base.endswith('/') and not path.startswith('/'):
        return base + '/' + path
    return base + path

def _arg_block_at(code: str, start_idx: int) -> Tuple[str, int]:
    """
    Bir method çağrısının '(' konumundan başlayarak, kapanan ')' noktasına kadar
    olan argüman bloğunu (parantez dengeleme ile) döndürür.
    """
    assert code[start_idx] == '('
    i = start_idx
    depth = 0
    in_squote = in_dquote = in_template = False
    escape = False
    while i < len(code):
        ch = code[i]
        if escape:
            escape = False
            i += 1
            continue
        if ch == '\\':
            escape = True
            i += 1
            continue

        if in_template:
            if ch == '`':
                in_template = False
            i += 1
            continue

        if in_squote:
            if ch == "'":
                in_squote = False
            i += 1
            continue

        if in_dquote:
            if ch == '"':
                in_dquote = False
            i += 1
            continue

        if ch == "'":
            in_squote = True
        elif ch == '"':
            in_dquote = True
        elif ch == '`':
            in_template = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                # argümanlar: code[start_idx+1:i], ve kapanış i konumunda
                return code[start_idx+1:i], i
        i += 1

    # Eşleşmedi: hatalı JS
    return "", start_idx

def _extract_path_from_args(arg_str: str) -> str:
    m = RE_FIRST_ARG_PATH.search(arg_str)
    if not m:
        return ""
    return m.group('spath') or m.group('tpath') or ""

def _extract_roles_from_args(arg_str: str) -> List[str]:
    roles = [mm.group('role') for mm in RE_CHECK_ROLE.finditer(arg_str)]
    
    dedup = []
    for r in roles:
        if r not in dedup:
            dedup.append(r)
    return dedup

def _line_no(code: str, idx: int) -> int:
    return code.count('\n', 0, idx) + 1

def parse_express_code(js_code: str, filename: str = "<memory>") -> List[Dict]:
    results: List[Dict] = []

    app_vars = _find_var_names(RE_APP_VARS, js_code) or ["app"]  
    router_vars = _find_var_names(RE_ROUTER_VARS, js_code)
    mounts = _find_mounts(js_code)  # (appVar, base, routerVar)

    # Router mount base path haritası
    base_by_router = {}
    for app_var, base, rvar in mounts:
        base_by_router.setdefault(rvar, []).append(base)  # aynı router birden fazla yerde mount olabilir

    # --- 1) route chain kalıbı: router.route('/x').get(...).post(...) ---
    for m in RE_ROUTE_CHAIN.finditer(js_code):
        obj = m.group('obj')
        raw_path = (m.group('spath') or m.group('tpath') or "")
        chain = m.group('chain')
        base_prefixes = base_by_router.get(obj, [""]) if obj in router_vars else [""]

        # zincirin içinde tek tek .get(...), .post(...), ... bloklarını yakala
        for m2 in re.finditer(r'\.(?P<method>get|post|put|delete|patch|options|all)\s*\(', chain):
            method = m2.group('method').upper()
            
            global_idx = m.start('chain') + m2.start()
            
            open_paren_idx = js_code.find('(', global_idx)
            arg_str, close_idx = _arg_block_at(js_code, open_paren_idx)
            roles = _extract_roles_from_args(arg_str)
            if not roles:
               
                
                roles = []

            line_no = _line_no(js_code, m.start())
            for base in base_prefixes:
                full_path = _combine_paths(base, raw_path)
                results.append({
                    "file": filename,
                    "line": line_no,
                    "source": obj,
                    "method": method,
                    "path": full_path,
                    "roles": roles,
                    "role": roles[0] if roles else None,  # geri uyumluluk için
                })

    # --- 2) basit çağrılar: app.get('/x', ...), router.post('/y', ...) ---
    for m in RE_SIMPLE_CALL_HEAD.finditer(js_code):
        obj = m.group('obj')
        method = m.group('method').upper()

        
        open_paren_idx = js_code.find('(', m.end() - 1)
        if open_paren_idx == -1:
            continue
        arg_str, close_idx = _arg_block_at(js_code, open_paren_idx)
        if not arg_str:
            continue

        raw_path = _extract_path_from_args(arg_str)
        roles = _extract_roles_from_args(arg_str)
        line_no = _line_no(js_code, m.start())

        
        if raw_path == "":
            continue

        
        if obj in router_vars:
            bases = base_by_router.get(obj, [""])
        else:
           
            bases = [""]

        for base in bases:
            full_path = _combine_paths(base, raw_path)
            results.append({
                "file": filename,
                "line": line_no,
                "source": obj,
                "method": method,
                "path": full_path,
                "roles": roles,
                "role": roles[0] if roles else None,
            })

    return results
