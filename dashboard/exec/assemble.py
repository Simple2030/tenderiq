"""Joins the shell, the page and the shim into template.html (data is inlined by build.py)."""
from pathlib import Path
H = Path(__file__).resolve().parent
head, css, body = (H / "shell_head.html").read_text(), (H / "page_css.html").read_text(), (H / "page_body.html").read_text()
js, shim = (H / "page_script.js").read_text(), (H / "shim.js").read_text()
(H / "template.html").write_text(f'''{head}
{css}
<div id="dash-root">
{body.strip()}
<footer class="brandfoot"><span>רביד לירז · אסטרטגיה וכלכלת נדל״ן</span><span>נתונים: רשות מקרקעי ישראל, API אתר המכרזים</span></footer>
</div>
<script>window.EMBED = __DATA__;</script>
<script>
{shim}
</script>
<script>
{js}
document.getElementById('m-cov') && (document.getElementById('m-cov').textContent = window.EMBED.meta.tenders_fetched.toLocaleString('he-IL'));
</script>
''')
