"""Loopback-only synthetic Mijn Dossier page for visible computer-use demos."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PAGE = b"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mijn Dossier - Synthetic Training</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#243447;background:#eef3f7}
*{box-sizing:border-box}body{margin:0}.training{background:#7b1fa2;color:white;padding:9px 24px;font-weight:700;text-align:center}
header{background:white;border-bottom:1px solid #ccd6df;padding:18px 34px;display:flex;justify-content:space-between;align-items:center}
.brand{font-size:24px;font-weight:700;color:#006a71}.patient{font-weight:650}.patient small{display:block;color:#627483;font-weight:500}
main{max-width:1050px;margin:28px auto;padding:0 24px}.card{background:white;border:1px solid #d5dee6;border-radius:10px;padding:26px;box-shadow:0 3px 12px #26323814}
.identity{background:#fff8d9;border:3px solid #7b1fa2;border-radius:10px;margin-bottom:20px;padding:16px 22px;text-align:center}
.identity span{display:block;font-size:15px;font-weight:700;letter-spacing:.04em}.identity strong{display:block;color:#4a0d61;font-size:30px;margin:4px 0}
h1{margin-top:0;font-size:28px}p{line-height:1.5}.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:22px}
button{font:inherit;cursor:pointer}.tile,.primary{border:2px solid #007f86;background:white;color:#075d62;border-radius:9px;padding:22px;text-align:left;font-weight:700;font-size:18px}
.tile:hover,.primary:hover{background:#e5f7f8}.primary{display:inline-block;padding:14px 22px}.back{border:0;background:transparent;color:#006a71;padding:8px 0;margin-bottom:12px}
.hidden{display:none}.result-list{display:grid;gap:12px;margin-top:20px}.result-row{border:1px solid #d4dde5;border-radius:8px;padding:16px;display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:12px;align-items:center}
.name{font-weight:700}.normal{color:#2e7d32;font-weight:700}.date{color:#607482}footer{max-width:1050px;margin:16px auto;padding:0 24px;color:#667784;font-size:13px}
</style>
</head>
<body data-patient-id="DEMO-100042">
<div class="training">SYNTHETIC TRAINING DATA - NOT A REAL PATIENT RECORD</div>
<header><div class="brand">Amsterdam UMC | Mijn Dossier</div><div class="patient">Demo Patient<small>Patient ID: DEMO-100042</small></div></header>
<main>
  <div class="identity">
    <span>REQUESTED SYNTHETIC PATIENT</span>
    <strong>Patient ID: DEMO-100042</strong>
    <span>Exact identity shown for this training scenario</span>
  </div>
  <section id="home" class="card">
    <h1>Goedemorgen</h1><p>Bekijk uw afspraken, berichten en onderzoeksresultaten.</p>
    <div class="tiles">
      <button class="tile" type="button">Afspraken</button>
      <button id="uitslagen-button" class="tile" type="button">Uitslagen</button>
      <button class="tile" type="button">Berichten</button>
    </div>
  </section>
  <section id="results-overview" class="card hidden">
    <button class="back" data-target="home" type="button">&larr; Terug</button>
    <h1>Uitslagen</h1><p>Kies een categorie om bestaande resultaten te bekijken.</p>
    <button id="blood-button" class="primary" type="button">Bloedonderzoek</button>
  </section>
  <section id="blood-results" class="card hidden">
    <button class="back" data-target="results-overview" type="button">&larr; Uitslagen</button>
    <h1>Bloedonderzoek</h1>
    <p>Afgenomen op 18 september 2026. Alle waarden hieronder zijn synthetisch.</p>
    <div class="result-list">
      <div class="result-row"><div class="name">Hemoglobine</div><div>8.6 mmol/L</div><div>7.5 - 10.0</div><div class="normal">Normaal</div></div>
      <div class="result-row"><div class="name">Leukocyten</div><div>6.4 x10^9/L</div><div>4.0 - 10.0</div><div class="normal">Normaal</div></div>
      <div class="result-row"><div class="name">CRP</div><div>2 mg/L</div><div>0 - 5</div><div class="normal">Normaal</div></div>
      <div class="result-row"><div class="name">Creatinine</div><div>78 umol/L</div><div>60 - 110</div><div class="normal">Normaal</div></div>
      <div class="result-row"><div class="name">Glucose</div><div>5.1 mmol/L</div><div>3.5 - 7.8</div><div class="normal">Normaal</div></div>
    </div>
  </section>
</main>
<footer>Independent synthetic computer-use demonstration. No connection to Amsterdam UMC or Epic production systems.</footer>
<script>
const sections=[...document.querySelectorAll("main>section")];
function show(id){sections.forEach(x=>x.classList.toggle("hidden",x.id!==id))}
document.querySelector("#uitslagen-button").onclick=()=>show("results-overview");
document.querySelector("#blood-button").onclick=()=>show("blood-results");
document.querySelectorAll(".back").forEach(x=>x.onclick=()=>show(x.dataset.target));
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "SyntheticEpicPortal"

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/healthz":
            body = b'{"status":"ok"}'
            content_type = "application/json"
        elif self.path in {"/", "/index.html"}:
            body = PAGE
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Loopback synthetic Epic training portal.")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Synthetic Epic portal: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
