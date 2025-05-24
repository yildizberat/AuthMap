
from accessmap.core.analyzer import analyze_project
from accessmap.exporter.csv_exporter import export_to_csv
import sys

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Kullanım: python main.py <proje_klasörü>")
    else:
        path = sys.argv[1]
        routes = analyze_project(path)
        export_to_csv(routes)
        print("✅ CSV oluşturuldu. Toplam rota:", len(routes))
