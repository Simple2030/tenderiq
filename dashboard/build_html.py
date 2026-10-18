"""Inline dashboard/data.json into dashboard/template.html -> dashboard/index.html."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
html = (HERE / "template.html").read_text(encoding="utf-8")
data = (HERE / "data.json").read_text(encoding="utf-8").replace("</", "<\\/")
(HERE / "index.html").write_text(html.replace("__DATA__", data), encoding="utf-8")
print(HERE / "index.html")
