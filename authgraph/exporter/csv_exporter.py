import csv

def export_to_csv(routes, filename="permissions.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["role", "path", "method"])
        writer.writeheader()
        for route in routes:
            writer.writerow(route)