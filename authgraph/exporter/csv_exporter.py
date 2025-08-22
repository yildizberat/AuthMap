import csv
import os


def _stringify(value):
    if isinstance(value, (list, tuple)):
        return ";".join(map(str, value))
    return value if value is not None else ""

def export_to_csv(routes, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Gelen tüm kayıtların anahtarlarının birleşimi
    all_keys = set()
    for r in routes or []:
        all_keys.update(r.keys())

   
    preferred = ["file", "line", "source", "method", "path", "role", "roles", "status", "count", "last_seen"]
    headers = [k for k in preferred if k in all_keys] + [k for k in sorted(all_keys) if k not in preferred]

    # Hiç kayıt yoksa en azından çekirdek kolonları yaz
    if not headers:
        headers = ["method", "path", "role"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in routes or []:
            row = {h: _stringify(r.get(h, "")) for h in headers}
            writer.writerow(row)
