import csv
import sqlite3

# الاتصال بقاعدة البيانات
conn = sqlite3.connect("gym_tracker.db")
cursor = conn.cursor()

# 1. استعلام لجلب أسماء جميع الجداول الموجودة في قاعدة البيانات
cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE"
    " 'sqlite_%';"
)
tables = cursor.fetchall()

if not tables:
    print("[-] لا توجد أي جداول داخل قاعدة البيانات!")
else:
    print(f"[+] الجداول المكتشفة: {[t[0] for t in tables]}")

    # 2. حلقة تكرارية لسحب وتصدير كل جدول على حدة
    for table_tuple in tables:
      table_name = table_tuple[0]
      try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        headers = [description[0] for description in cursor.description]

        output_file = f"{table_name}_export.csv"
        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
          writer = csv.writer(f)
          writer.writerow(headers)
          writer.writerows(rows)

        print(
            f"[✓] تم تصدير الجدول '{table_name}' بنجاح ({len(rows)} سجل) ->"
            f" {output_file}"
        )

      except Exception as e:
        print(f"[-] فشل تصدير الجدول '{table_name}': {e}")

conn.close()
