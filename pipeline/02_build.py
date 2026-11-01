"""Step 2: clean records and build daily series (sql/01_clean.sql), then pick origin hubs."""
import os
import runpy

from common import ROOT, SQL, connect


def main():
    os.chdir(ROOT)  # SQL uses project-relative paths
    con = connect()
    con.execute((SQL / "01_clean.sql").read_text(encoding="utf-8"))
    print(con.execute("SELECT * FROM dq_clean").df().to_string(index=False))
    con.close()
    runpy.run_path(str(ROOT / "pipeline" / "20_hubs.py"), run_name="__main__")


if __name__ == "__main__":
    main()
