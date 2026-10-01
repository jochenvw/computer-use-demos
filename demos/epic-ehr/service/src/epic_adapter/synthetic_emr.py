"""Loopback-only synthetic clinician EMR ("SanitaCartella") and PACS viewer.

An invented, deliberately dated Italian hospital workstation for visible
computer-use demos: worklist, patient search, chart with Oncology and Surgery
views, Labs / Imaging / Notes tabs, and a PACS viewer with a synthetic MRI
series and its signed report. Every value is invented; nothing is real.
Server-side rendered, no JavaScript, no external resources.
"""
from __future__ import annotations

import argparse
import html
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

PRODUCT = "SanitaCartella 4.2"
HOSPITAL = "Ospedale di Montalcino"
PACS_PRODUCT = "MontalcinoPACS Web 2.1"
PAGE_TITLE = "Ospedale di Montalcino - Postazione clinica"
BANNER = "SYNTHETIC TRAINING DATA - NOT A REAL PATIENT RECORD"
OPERATOR = "DR.BELLINI (Chirurgia Generale)"
ANNA_ID = "TUS-2026-0417"

# --- Synthetic patients -------------------------------------------------------
# lab row: (date, test, value, unit, range, flag)
PATIENTS: dict[str, dict] = {
    ANNA_ID: {
        "cognome": "RICCI", "nome": "Anna", "sesso": "F", "nascita": "14/03/1971",
        "eta": 55, "residenza": "Utrecht (NL) - turista", "reparto": "Chirurgia Generale",
        "letto": "12", "ricovero": "18/09/2026", "nosologico": "2026/004417",
        "medico": "Dr. M. Bellini", "stato": "Trasferita a UMC Utrecht (NL) il 23/09/2026",
        "allergie": "Nessuna allergia nota",
        "motivo": "Sincope in vacanza (Montalcino) con anemia severa",
        "problemi": [
            ("153.3", "Neoplasia maligna del sigma (adenocarcinoma, biopsia 19/09/2026)"),
            ("197.7", "Lesioni epatiche secondarie sospette (RM 21/09/2026)"),
            ("280.0", "Anemia sideropenica da perdita ematica cronica"),
            ("780.2", "Sincope e collasso"),
        ],
        "terapia": [
            ("Ferro carbossimaltosio", "1000 mg", "e.v.", "dose unica 20/09/2026"),
            ("Pantoprazolo", "40 mg", "e.v.", "1 volta/die"),
            ("Enoxaparina", "4000 UI", "s.c.", "1 volta/die"),
        ],
        "labs": [
            ("18/09/2026 23:05", "Emoglobina", "8.1", "g/dL", "12.0 - 16.0", "L"),
            ("18/09/2026 23:05", "MCV", "71", "fL", "80 - 100", "L"),
            ("18/09/2026 23:05", "Leucociti", "7.2", "10^3/uL", "4.0 - 10.0", ""),
            ("18/09/2026 23:05", "Piastrine", "412", "10^3/uL", "150 - 400", "H"),
            ("18/09/2026 23:05", "Creatinina", "0.8", "mg/dL", "0.5 - 1.1", ""),
            ("18/09/2026 23:05", "Proteina C reattiva", "6.1", "mg/L", "0 - 5.0", "H"),
            ("19/09/2026 07:30", "Ferritina", "6", "ng/mL", "15 - 150", "L"),
            ("19/09/2026 07:30", "CEA", "18.4", "ng/mL", "0 - 5.0", "H"),
            ("19/09/2026 07:30", "CA 19-9", "41", "U/mL", "0 - 37", "H"),
            ("21/09/2026 07:15", "Emoglobina", "10.2", "g/dL", "12.0 - 16.0", "L"),
        ],
        "vitali": [
            ("18/09/2026 22:40", "98/60", "104", "97", "36.4"),
            ("19/09/2026 08:00", "120/80", "84", "98", "36.6"),
            ("22/09/2026 08:00", "118/76", "78", "98", "36.5"),
        ],
        "oncologia": {
            "diagnosi": "Adenocarcinoma del sigma, moderatamente differenziato (G2)",
            "stadio": "cT3 cN1 M1 (fegato) - stadiazione clinica provvisoria",
            "biomarcatori": "KRAS / NRAS / BRAF / MSI: richiesti 22/09/2026 - in corso",
            "marcatori": "CEA 18.4 ng/mL (H) - CA 19-9 41 U/mL (H) - 19/09/2026",
            "piano": "Discussione multidisciplinare (MDT) presso centro di riferimento; "
                     "nessuna terapia oncologica avviata a Montalcino.",
        },
        "chirurgia": {
            "valutazione": "Consulenza 19/09/2026: addome trattabile, non segni di "
                           "occlusione o perforazione. ASA II.",
            "interventi": "Nessun intervento chirurgico eseguito.",
            "procedure": "Colonscopia 19/09/2026: neoformazione stenosante del sigma a "
                         "25 cm, biopsie multiple. Emotrasfusione 2 unita' EC 19/09/2026.",
            "indicazione": "Nessuna indicazione chirurgica in urgenza; rivalutazione "
                           "dopo MDT.",
        },
        "note": [
            ("18/09/2026 22:40", "Verbale Pronto Soccorso", "Dr.ssa C. Neri",
             "Donna di 55 anni, turista olandese, sincope durante passeggiata. "
             "Pallore, astenia da settimane. PA 98/60, FC 104. Hb 8.1 g/dL. "
             "Ricovero in Chirurgia Generale."),
            ("19/09/2026 12:10", "Consulenza chirurgica", "Dr. M. Bellini",
             "Addome trattabile, non occlusione. Colonscopia: neoformazione stenosante "
             "del sigma, biopsie inviate. Trasfuse 2 unita' EC."),
            ("22/09/2026 10:30", "Consulenza oncologica", "Dr.ssa L. Santoro",
             "Istologico: adenocarcinoma G2. TC e RM: due lesioni epatiche sospette. "
             "Richiesti biomarcatori. Indicata discussione MDT."),
            ("23/09/2026 09:00", "Lettera di trasferimento", "Dr. M. Bellini",
             "Paziente stabile, trasferita su richiesta della famiglia presso "
             "UMC Utrecht (NL) per prosecuzione dell'iter diagnostico-terapeutico."),
        ],
        "studi": ["MTL-26-08817", "MTL-26-08790"],
    },
    "TUS-2026-0398": {
        "cognome": "CONTI", "nome": "Bruno", "sesso": "M", "nascita": "02/11/1948",
        "eta": 77, "residenza": "Siena", "reparto": "Medicina Interna", "letto": "4",
        "ricovero": "15/09/2026", "nosologico": "2026/004398", "medico": "Dr. P. Fanti",
        "stato": "Ricoverato", "allergie": "Penicillina",
        "motivo": "Scompenso cardiaco riacutizzato",
        "problemi": [("428.0", "Insufficienza cardiaca congestizia")],
        "terapia": [("Furosemide", "40 mg", "e.v.", "2 volte/die")],
        "labs": [("15/09/2026 10:00", "Creatinina", "1.4", "mg/dL", "0.7 - 1.2", "H")],
        "vitali": [("15/09/2026 09:30", "142/88", "92", "93", "36.8")],
        "note": [("15/09/2026 11:00", "Diario clinico", "Dr. P. Fanti",
                  "Dispnea da sforzo, edemi declivi. Avviata terapia diuretica.")],
        "studi": [],
    },
    "TUS-2026-0402": {
        "cognome": "MARINO", "nome": "Giuseppina", "sesso": "F", "nascita": "27/06/1939",
        "eta": 87, "residenza": "Buonconvento", "reparto": "Oncologia", "letto": "2",
        "ricovero": "16/09/2026", "nosologico": "2026/004402", "medico": "Dr.ssa L. Santoro",
        "stato": "Ricoverata", "allergie": "Nessuna allergia nota",
        "motivo": "Neutropenia febbrile",
        "problemi": [("174.9", "Neoplasia maligna della mammella")],
        "terapia": [("Piperacillina/tazobactam", "4.5 g", "e.v.", "3 volte/die")],
        "labs": [("16/09/2026 08:00", "Neutrofili", "0.4", "10^3/uL", "1.5 - 7.0", "L")],
        "vitali": [("16/09/2026 07:45", "110/70", "98", "96", "38.4")],
        "note": [("16/09/2026 09:00", "Diario clinico", "Dr.ssa L. Santoro",
                  "Febbre dopo terzo ciclo. Emocolture eseguite.")],
        "studi": [],
    },
    "TUS-2026-0411": {
        "cognome": "FERRARO", "nome": "Luca", "sesso": "M", "nascita": "09/01/1985",
        "eta": 41, "residenza": "Montalcino", "reparto": "Ortopedia", "letto": "7",
        "ricovero": "19/09/2026", "nosologico": "2026/004411", "medico": "Dr. G. Rossi",
        "stato": "Dimesso il 21/09/2026", "allergie": "Nessuna allergia nota",
        "motivo": "Frattura di polso destro",
        "problemi": [("813.4", "Frattura distale del radio")],
        "terapia": [("Paracetamolo", "1 g", "os", "al bisogno")],
        "labs": [("19/09/2026 14:00", "Emoglobina", "14.6", "g/dL", "13.0 - 17.0", "")],
        "vitali": [("19/09/2026 13:30", "125/80", "76", "99", "36.5")],
        "note": [("19/09/2026 15:00", "Verbale operatorio", "Dr. G. Rossi",
                  "Riduzione e sintesi con placca volare.")],
        "studi": [],
    },
    "TUS-2026-0419": {
        "cognome": "RICCI", "nome": "Antonio", "sesso": "M", "nascita": "30/07/1962",
        "eta": 64, "residenza": "Pienza", "reparto": "Cardiologia", "letto": "9",
        "ricovero": "17/09/2026", "nosologico": "2026/004419", "medico": "Dr. F. Galli",
        "stato": "Ricoverato", "allergie": "Mezzo di contrasto iodato",
        "motivo": "Dolore toracico",
        "problemi": [("411.1", "Sindrome coronarica intermedia")],
        "terapia": [("Acido acetilsalicilico", "100 mg", "os", "1 volta/die")],
        "labs": [("17/09/2026 06:00", "Troponina I hs", "34", "ng/L", "0 - 16", "H")],
        "vitali": [("17/09/2026 05:40", "150/90", "88", "97", "36.6")],
        "note": [("17/09/2026 07:00", "Diario clinico", "Dr. F. Galli",
                  "Dolore toracico regredito. Programmata coronarografia.")],
        "studi": ["MTL-26-08702"],
    },
    "TUS-2026-0421": {
        "cognome": "GALLI", "nome": "Maria Teresa", "sesso": "F", "nascita": "15/05/1957",
        "eta": 69, "residenza": "San Quirico d'Orcia", "reparto": "Oncologia",
        "letto": "DH", "ricovero": "22/09/2026", "nosologico": "2026/004421",
        "medico": "Dr.ssa L. Santoro", "stato": "Day hospital",
        "allergie": "Nessuna allergia nota", "motivo": "Chemioterapia programmata",
        "problemi": [("162.9", "Neoplasia maligna del polmone")],
        "terapia": [("Carboplatino", "AUC 5", "e.v.", "ogni 21 giorni")],
        "labs": [("22/09/2026 08:00", "Piastrine", "188", "10^3/uL", "150 - 400", "")],
        "vitali": [("22/09/2026 08:10", "130/82", "80", "96", "36.4")],
        "note": [("22/09/2026 09:30", "Diario DH", "Dr.ssa L. Santoro",
                  "Ciclo 4 somministrato senza eventi avversi.")],
        "studi": [],
    },
}

MRI_REPORT = (
    "RM FEGATO SENZA E CON MEZZO DI CONTRASTO",
    "Quesito: stadiazione in paziente con neoformazione del sigma "
    "(biopsia: adenocarcinoma).",
    "Tecnica: sequenze assiali T2 HASTE, DWI b50-b800, T1 VIBE dinamiche "
    "prima e dopo mezzo di contrasto (gadolinio).",
    "Reperti: nel segmento VII lesione nodulare di 22 x 19 mm, ipointensa in T1, "
    "moderatamente iperintensa in T2, con restrizione della diffusione ed "
    "enhancement periferico ad anello. Nel segmento IVa seconda lesione di 14 mm "
    "con analoghe caratteristiche. Non dilatazione delle vie biliari. Vena porta "
    "pervia. Milza, pancreas e surreni nei limiti. Non versamento ascitico.",
    "Conclusioni: due lesioni epatiche (segmento VII 22 mm, segmento IVa 14 mm) "
    "compatibili con localizzazioni secondarie. Si consiglia discussione "
    "multidisciplinare.",
)
CT_REPORT = (
    "TC TORACE-ADDOME CON MEZZO DI CONTRASTO",
    "Quesito: stadiazione, anemia sideropenica.",
    "Reperti: ispessimento parietale stenosante del sigma per circa 5 cm con "
    "linfonodi pericolici fino a 9 mm. Due aree ipodense epatiche (segmenti VII e "
    "IVa), da caratterizzare con RM. Polmoni senza noduli. Non versamento.",
    "Conclusioni: neoformazione del sigma con linfoadenopatia locoregionale; "
    "lesioni epatiche da caratterizzare con RM.",
)
STUDIES: dict[str, dict] = {
    "MTL-26-08817": {
        "patient": ANNA_ID, "data": "21/09/2026 15:20", "modalita": "MR",
        "descrizione": "RM fegato senza e con mdc", "report": MRI_REPORT,
        "refertatore": "Dott.ssa Elena Fabbri", "firmato": "21/09/2026 16:42",
        "serie": [("AX T2 HASTE", 12), ("AX T1 VIBE post-contrasto (fase venosa)", 12)],
    },
    "MTL-26-08790": {
        "patient": ANNA_ID, "data": "20/09/2026 11:05", "modalita": "CT",
        "descrizione": "TC torace-addome con mdc", "report": CT_REPORT,
        "refertatore": "Dott. Andrea Lupi", "firmato": "20/09/2026 13:10",
        "serie": [("AX addome venosa 5 mm", 12)],
    },
    "MTL-26-08702": {
        "patient": "TUS-2026-0419", "data": "17/09/2026 06:30", "modalita": "CR",
        "descrizione": "RX torace", "report": (
            "RX TORACE", "Conclusioni: non addensamenti parenchimali in atto."),
        "refertatore": "Dott. Andrea Lupi", "firmato": "17/09/2026 08:02",
        "serie": [("PA", 1)],
    },
}

# --- Rendering ------------------------------------------------------------------
CSS = """
body{margin:0;background:#d4d0c8;font:12px Tahoma,Verdana,Arial,sans-serif;color:#000}
a{color:#00309c}a:visited{color:#00309c}
.synthetic{background:repeating-linear-gradient(45deg,#ffd800 0 14px,#111 14px 28px);padding:3px}
.synthetic div{background:#b00000;color:#fff;font:bold 15px Verdana,Arial,sans-serif;text-align:center;padding:5px;letter-spacing:1px}
.titlebar{background:linear-gradient(90deg,#0a246a,#a6caf0);color:#fff;font-weight:bold;padding:4px 8px}
.menubar{background:#d4d0c8;border-bottom:1px solid #808080;padding:3px 6px}
.menubar a,.menubar span{margin-right:14px;color:#000;text-decoration:none}
.apps{background:#ece9d8;border-bottom:2px groove #fff;padding:4px 6px}
.apps a{display:inline-block;margin-right:6px;padding:3px 10px;border:2px outset #fff;background:#d4d0c8;color:#000;text-decoration:none}
.apps a.on{border-style:inset;background:#c0c0c0;font-weight:bold}
.wrap{padding:8px}
.box{background:#fff;border:1px solid #808080;margin-bottom:8px}
.box h3{margin:0;padding:3px 6px;font-size:12px;border-bottom:1px solid #808080;background:linear-gradient(#e6ecf8,#c3d1ee)}
.box.pink h3{background:linear-gradient(#f8e6ea,#e9c0c8)}.box.sand h3{background:linear-gradient(#f4eedc,#ddd0a6)}
.box.green h3{background:linear-gradient(#e6f4e6,#bcdcbc)}.box .in{padding:6px;overflow:hidden}
table.grid{border-collapse:collapse;width:100%}
table.grid th{background:#ece9d8;border:1px solid #a0a0a0;text-align:left;padding:2px 5px;font-weight:bold}
table.grid td{border:1px solid #c8c8c8;padding:2px 5px;vertical-align:top}
table.grid tr:nth-child(even) td{background:#f4f7fc}
.flagL,.flagH{color:#c00000;font-weight:bold}
.banner{background:#2b4c7e;color:#fff;padding:6px 10px;display:flex;gap:28px;align-items:center}
.banner b{font-size:20px;letter-spacing:.5px}.banner small{display:block;color:#c6d4ea}
.toolbar{background:#ece9d8;border-bottom:1px solid #808080;padding:4px 6px}
.toolbar a{display:inline-block;margin-right:4px;padding:3px 10px;border:2px outset #fff;background:#d4d0c8;color:#000;text-decoration:none}
.toolbar a.on{border-style:inset;background:#bcbcbc;font-weight:bold}
.vista{float:right}.cols{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.foto{width:84px;height:100px;border:1px solid #808080;background:#e0e0e0;color:#606060;text-align:center;font-size:10px;padding-top:40px;box-sizing:border-box;float:left;margin-right:10px}
dl.kv{margin:0;display:grid;grid-template-columns:150px 1fr;gap:2px 8px}dl.kv dt{color:#555}dl.kv dd{margin:0}
.status{position:fixed;bottom:0;left:0;right:0;background:#d4d0c8;border-top:2px groove #fff;padding:2px 8px;font-size:11px;color:#333}
form.search input[type=text]{width:240px;border:2px inset #fff;padding:2px;font:12px Tahoma,Arial}
form.search button{border:2px outset #fff;background:#d4d0c8;font:12px Tahoma,Arial;padding:2px 10px}
.note{border-bottom:1px dotted #999;padding:5px 0}.note b{color:#0a246a}
.foot{color:#555;font-size:11px;margin:10px 0 40px}
.pacs{background:#1b1b1b;color:#ddd}.pacs .box{background:#262626;border-color:#555;color:#ddd}
.pacs .box h3{background:linear-gradient(#4a4a4a,#2e2e2e);color:#eee;border-color:#555}
.pacs table.grid td{border-color:#444}.pacs table.grid th{background:#3a3a3a;color:#eee;border-color:#555}
.pacs table.grid tr:nth-child(even) td{background:#2c2c2c}.pacs a{color:#7fb2ff}
.pacs .apps,.pacs .menubar,.pacs .apps a{color:#000}
.viewer{display:grid;grid-template-columns:200px 520px 1fr;gap:8px}
.thumbs a{display:block;margin-bottom:6px;color:#ddd;text-decoration:none;border:1px solid #444;padding:3px}
.thumbs a.on{border-color:#ffd800}.thumbs img{width:180px;height:180px;display:block}
.slices a{display:inline-block;min-width:22px;text-align:center;border:1px solid #555;margin:1px;color:#ddd;text-decoration:none}
.slices a.on{background:#ffd800;color:#000}
.report p{margin:0 0 8px;line-height:1.45}.signed{color:#9fd49f;font-weight:bold}
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def _page(body: str, *, pacs: bool = False, app: str = "emr") -> bytes:
    apps = (
        f'<div class="apps">Applicazioni postazione: '
        f'<a href="/" class="{"on" if app == "emr" else ""}">{PRODUCT} - Cartella clinica</a>'
        f'<a href="/pacs" class="{"on" if app == "pacs" else ""}">{PACS_PRODUCT} - Immagini</a>'
        f'</div>'
    )
    title = PACS_PRODUCT if app == "pacs" else PRODUCT
    page = (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        f"<title>{esc(PAGE_TITLE)}</title><style>{CSS}</style></head>"
        f'<body class="{"pacs" if pacs else ""}">'
        f'<div class="synthetic"><div>{BANNER}</div></div>'
        f'<div class="titlebar">{esc(title)} - {HOSPITAL} - utente: {OPERATOR}</div>'
        '<div class="menubar"><span>File</span><span>Modifica</span><span>Visualizza</span>'
        '<span>Strumenti</span><span>Finestra</span><span>?</span></div>'
        f'{apps}<div class="wrap">{body}'
        '<p class="foot">Sistema di addestramento sintetico. Tutti i pazienti, i valori e le '
        'immagini sono inventati. Nessun collegamento con sistemi ospedalieri reali.</p>'
        '</div><div class="status">Pronto | Server: SCART-SRV01 | Postazione: '
        'CHIR-PC07 | Sola lettura</div></body></html>'
    )
    return page.encode("utf-8")


def _name(patient: dict) -> str:
    return f"{patient['cognome']}, {patient['nome']}"


def _matches(patient_id: str, patient: dict, query: str) -> bool:
    words = query.lower().replace(",", " ").split()
    haystack = f"{patient_id} {patient['cognome']} {patient['nome']}".lower()
    return all(word in haystack for word in words)


def worklist(query: str = "") -> bytes:
    rows = []
    for patient_id, patient in PATIENTS.items():
        if query and not _matches(patient_id, patient, query):
            continue
        rows.append(
            f"<tr><td><a href=\"/paziente/{quote(patient_id)}\">{esc(_name(patient))}</a></td>"
            f"<td>{esc(patient_id)}</td><td>{esc(patient['sesso'])}</td>"
            f"<td>{esc(patient['nascita'])}</td><td>{esc(patient['reparto'])}</td>"
            f"<td>{esc(patient['letto'])}</td><td>{esc(patient['ricovero'])}</td>"
            f"<td>{esc(patient['stato'])}</td></tr>"
        )
    table = (
        '<table class="grid"><tr><th>Paziente</th><th>ID paziente</th><th>Sesso</th>'
        '<th>Data di nascita</th><th>Reparto</th><th>Letto</th><th>Ricovero</th>'
        '<th>Stato</th></tr>' + ("".join(rows) or
                                 '<tr><td colspan="8">Nessun paziente trovato.</td></tr>')
        + "</table>"
    )
    body = (
        '<div class="box"><h3>Ricerca paziente</h3><div class="in">'
        '<form class="search" method="get" action="/">Cognome, nome o ID paziente: '
        f'<input type="text" name="q" value="{esc(query)}" autocomplete="off"> '
        '<button type="submit">Cerca</button></form></div></div>'
        f'<div class="box"><h3>Lista di lavoro - tutti i reparti ({len(rows)} pazienti)</h3>'
        f'<div class="in">{table}</div></div>'
    )
    return _page(body)


TABS = (("riepilogo", "Riepilogo"), ("esami", "Esami di laboratorio"),
        ("imaging", "Imaging"), ("note", "Note cliniche"))
VIEWS = (("oncologia", "Oncologia"), ("chirurgia", "Chirurgia"))


def _rows(header: tuple[str, ...], rows: list[tuple]) -> str:
    head = "".join(f"<th>{esc(cell)}</th>" for cell in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<table class="grid"><tr>{head}</tr>{body or "<tr><td>-</td></tr>"}</table>'


def _box(title: str, inner: str, tone: str = "") -> str:
    return f'<div class="box {tone}"><h3>{esc(title)}</h3><div class="in">{inner}</div></div>'


def _kv(pairs: list[tuple[str, str]]) -> str:
    return '<dl class="kv">' + "".join(
        f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in pairs
    ) + "</dl>"


def _labs(patient: dict) -> str:
    rows = []
    for date, test, value, unit, ref, flag in patient["labs"]:
        css = f' class="flag{flag}"' if flag else ""
        rows.append(
            f"<tr><td>{esc(date)}</td><td>{esc(test)}</td><td{css}>{esc(value)}</td>"
            f"<td>{esc(unit)}</td><td>{esc(ref)}</td><td{css}>{esc(flag)}</td></tr>"
        )
    return (
        '<table class="grid"><tr><th>Data prelievo</th><th>Esame</th><th>Risultato</th>'
        '<th>Unita</th><th>Intervallo di riferimento</th><th>Flag</th></tr>'
        + "".join(rows) + "</table>"
    )


def chart(patient_id: str, view: str, tab: str) -> bytes | None:
    patient = PATIENTS.get(patient_id)
    if patient is None:
        return None
    view = view if view in dict(VIEWS) else "oncologia"
    tab = tab if tab in dict(TABS) else "riepilogo"
    base = f"/paziente/{quote(patient_id)}"
    banner = (
        f'<div class="banner"><span><b>{esc(_name(patient).upper())}</b>'
        f'<small>ID paziente: {esc(patient_id)}</small></span>'
        f'<span>Sesso: {esc(patient["sesso"])}<small>Nata/o il {esc(patient["nascita"])} '
        f'({patient["eta"]} anni)</small></span>'
        f'<span>Reparto: {esc(patient["reparto"])}<small>Letto {esc(patient["letto"])} - '
        f'nosologico {esc(patient["nosologico"])}</small></span>'
        f'<span>Allergie<small>{esc(patient["allergie"])}</small></span></div>'
    )
    tabs = "".join(
        f'<a href="{base}?vista={view}&amp;scheda={key}" class="{"on" if key == tab else ""}">'
        f"{label}</a>" for key, label in TABS
    )
    views = "".join(
        f'<a href="{base}?vista={key}&amp;scheda={tab}" class="{"on" if key == view else ""}">'
        f"Vista {label}</a>" for key, label in VIEWS
    )
    toolbar = (
        f'<div class="toolbar"><a href="/">&laquo; Lista pazienti</a>{tabs}'
        f'<span class="vista">{views}</span></div>'
    )
    if tab == "esami":
        content = _box("Esami di laboratorio", _labs(patient), "green")
    elif tab == "imaging":
        rows = []
        for accession in patient["studi"]:
            study = STUDIES[accession]
            rows.append(
                f"<tr><td>{esc(study['data'])}</td><td>{esc(study['modalita'])}</td>"
                f"<td>{esc(study['descrizione'])}</td><td>{esc(accession)}</td>"
                "<td>Refertato - referto e immagini in PACS</td>"
                f'<td><a href="/pacs/studio/{quote(accession)}">Apri in PACS &raquo;</a></td></tr>'
            )
        content = _box(
            "Imaging - richieste e studi",
            '<table class="grid"><tr><th>Data</th><th>Modalita</th><th>Descrizione</th>'
            '<th>Accession</th><th>Stato</th><th>Immagini</th></tr>'
            + ("".join(rows) or '<tr><td colspan="6">Nessuno studio.</td></tr>')
            + "</table>",
            "sand",
        )
    elif tab == "note":
        notes = "".join(
            f'<div class="note"><b>{esc(date)} - {esc(kind)}</b> ({esc(author)})<br>{esc(text)}</div>'
            for date, kind, author, text in patient["note"]
        )
        content = _box("Note cliniche e diario", notes, "pink")
    else:
        left = _box("Anagrafica", (
            '<div class="foto">FOTO<br>NON<br>DISPONIBILE</div>' + _kv([
                ("Cognome e nome", _name(patient)), ("ID paziente", patient_id),
                ("Data di nascita", patient["nascita"]), ("Sesso", patient["sesso"]),
                ("Residenza", patient["residenza"]),
            ])
        ))
        left += _box("Ricovero", _kv([
            ("Data ricovero", patient["ricovero"]), ("Reparto", patient["reparto"]),
            ("Medico referente", patient["medico"]), ("Motivo", patient["motivo"]),
            ("Stato", patient["stato"]),
        ]), "sand")
        right = _box("Problemi attivi (ICD-9-CM)", _rows(("Codice", "Descrizione"),
                                                         patient["problemi"]), "pink")
        right += _box("Terapia in corso", _rows(("Farmaco", "Dose", "Via", "Frequenza"),
                                                patient["terapia"]), "green")
        if view == "chirurgia":
            detail = patient.get("chirurgia")
            special = _box("Vista Chirurgia - valutazione chirurgica", _kv([
                ("Valutazione", detail["valutazione"]), ("Interventi", detail["interventi"]),
                ("Procedure", detail["procedure"]), ("Indicazione", detail["indicazione"]),
            ]) if detail else "Nessuna valutazione chirurgica registrata.")
            special += _box("Parametri vitali", _rows(
                ("Data/ora", "PA (mmHg)", "FC (bpm)", "SpO2 (%)", "T (C)"), patient["vitali"],
            ), "green")
        else:
            detail = patient.get("oncologia")
            special = _box("Vista Oncologia - quadro oncologico", _kv([
                ("Diagnosi", detail["diagnosi"]), ("Stadiazione", detail["stadio"]),
                ("Biomarcatori", detail["biomarcatori"]), ("Marcatori", detail["marcatori"]),
                ("Piano", detail["piano"]),
            ]) if detail else "Nessun percorso oncologico attivo.")
        content = f'<div class="cols"><div>{left}</div><div>{right}</div></div>{special}'
    return _page(banner + toolbar + f'<div style="margin-top:8px">{content}</div>')


def pacs_list(query: str = "") -> bytes:
    rows = []
    for accession, study in STUDIES.items():
        patient = PATIENTS[study["patient"]]
        if query and not _matches(study["patient"], patient, query):
            continue
        images = sum(count for _, count in study["serie"])
        rows.append(
            f"<tr><td>{esc(_name(patient))}</td><td>{esc(study['patient'])}</td>"
            f"<td>{esc(study['data'])}</td><td>{esc(study['modalita'])}</td>"
            f"<td>{esc(study['descrizione'])}</td><td>{images}</td><td>Firmato</td>"
            f'<td><a href="/pacs/studio/{quote(accession)}">Apri studio</a></td></tr>'
        )
    body = (
        '<div class="box"><h3>Ricerca studi</h3><div class="in">'
        '<form class="search" method="get" action="/pacs">Paziente (cognome o ID): '
        f'<input type="text" name="q" value="{esc(query)}" autocomplete="off"> '
        '<button type="submit">Cerca</button></form></div></div>'
        '<div class="box"><h3>Elenco studi</h3><div class="in"><table class="grid"><tr>'
        '<th>Paziente</th><th>ID paziente</th><th>Data studio</th><th>Mod.</th>'
        '<th>Descrizione</th><th>Immagini</th><th>Referto</th><th></th></tr>'
        + ("".join(rows) or '<tr><td colspan="8">Nessuno studio trovato.</td></tr>')
        + "</table></div></div>"
    )
    return _page(body, pacs=True, app="pacs")


def _int(value: str, default: int, low: int, high: int) -> int:
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


def viewer(accession: str, series: str, image: str) -> bytes | None:
    study = STUDIES.get(accession)
    if study is None:
        return None
    patient = PATIENTS[study["patient"]]
    series_index = _int(series, 1, 1, len(study["serie"]))
    name, count = study["serie"][series_index - 1]
    image_index = _int(image, (count + 1) // 2, 1, count)
    base = f"/pacs/studio/{quote(accession)}"
    thumbs = "".join(
        f'<a href="{base}?serie={n}" class="{"on" if n == series_index else ""}">'
        f'<img src="/pacs/img/{quote(accession)}/{n}/{(c + 1) // 2}.svg" alt="">'
        f"Serie {n}: {esc(label)} ({c} img)</a>"
        for n, (label, c) in enumerate(study["serie"], 1)
    )
    slices = "".join(
        f'<a href="{base}?serie={series_index}&amp;img={n}" class="{"on" if n == image_index else ""}">{n}</a>'
        for n in range(1, count + 1)
    )
    report = "".join(f"<p>{esc(line)}</p>" for line in study["report"])
    body = (
        f'<div class="box"><h3>{esc(_name(patient).upper())} - ID {esc(study["patient"])} - '
        f'{esc(patient["sesso"])} - nata/o il {esc(patient["nascita"])} | Studio '
        f'{esc(accession)} - {esc(study["descrizione"])} - {esc(study["data"])}</h3>'
        f'<div class="in"><a href="/pacs">&laquo; Elenco studi</a></div></div>'
        '<div class="viewer">'
        f'<div class="box"><h3>Serie</h3><div class="in thumbs">{thumbs}</div></div>'
        f'<div class="box"><h3>Serie {series_index}: {esc(name)} - immagine '
        f'{image_index}/{count}</h3><div class="in">'
        f'<img src="/pacs/img/{quote(accession)}/{series_index}/{image_index}.svg" '
        f'width="500" height="500" alt="Immagine sintetica">'
        f'<div class="slices">{slices}</div></div></div>'
        f'<div class="box report"><h3>Referto</h3><div class="in">{report}'
        f'<p class="signed">Firmato digitalmente: {esc(study["refertatore"])} - '
        f'{esc(study["firmato"])}</p></div></div></div>'
    )
    return _page(body, pacs=True, app="pacs")


def synthetic_image(accession: str, series: int, image: int) -> bytes | None:
    """Deterministic SVG phantom; anatomy is schematic, lesions follow the report."""
    study = STUDIES.get(accession)
    if study is None or not 1 <= series <= len(study["serie"]):
        return None
    label, count = study["serie"][series - 1]
    if not 1 <= image <= count:
        return None
    patient = PATIENTS[study["patient"]]
    modality = study["modalita"]
    t1_post = modality == "MR" and "T1" in label
    ct = modality in {"CT", "CR"}
    pos = (image - 0.5) / count
    tissue = "#7a7a7a" if ct else ("#6c6c6c" if t1_post else "#565656")
    fat = "#3a3a3a" if ct else "#c8c8c8"
    liver = "#8c8c8c" if ct else ("#9a9a9a" if t1_post else "#474747")
    bone = "#f0f0f0" if ct else "#2a2a2a"
    vessel = "#d8d8d8" if (ct or t1_post) else "#0a0a0a"
    liver_rx = 90 + 25 * math.sin(math.pi * pos)
    shapes = [
        '<rect width="512" height="512" fill="#000"/>',
        f'<ellipse cx="256" cy="270" rx="205" ry="150" fill="{fat}"/>',
        f'<ellipse cx="256" cy="270" rx="192" ry="138" fill="{tissue}"/>',
        f'<ellipse cx="{170 - pos * 10:.0f}" cy="245" rx="{liver_rx:.0f}" ry="92" fill="{liver}"/>',
        f'<ellipse cx="360" cy="{235 + pos * 10:.0f}" rx="38" ry="{40 + 15 * pos:.0f}" fill="{liver}"/>',
        f'<circle cx="256" cy="372" r="26" fill="{bone}"/>',
        f'<circle cx="280" cy="330" r="12" fill="{vessel}"/>',
        f'<circle cx="236" cy="322" r="11" fill="{vessel}"/>',
    ]
    if pos > 0.55:
        kidney = "#606060" if ct else "#8a8a8a"
        shapes += [f'<ellipse cx="180" cy="340" rx="26" ry="38" fill="{kidney}"/>',
                   f'<ellipse cx="335" cy="340" rx="26" ry="38" fill="{kidney}"/>']
    if accession in {"MTL-26-08817", "MTL-26-08790"}:
        # Segment VII (22 mm) on images 5-8, segment IVa (14 mm) on images 3-5.
        for first, last, radius, x, y in ((5, 8, 15.5, 128, 282), (3, 5, 10.0, 222, 196)):
            centre = (first + last) / 2
            if first <= image <= last:
                r = radius * math.sqrt(max(0.35, 1 - ((image - centre) / 2.6) ** 2))
                if ct:
                    shapes.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="#5c5c5c"/>')
                elif t1_post:
                    shapes.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="#4a4a4a" '
                                  'stroke="#e6e6e6" stroke-width="3"/>')
                else:
                    shapes.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="#a8a8a8"/>')
    text = "font-family:Consolas,monospace;font-size:13px;fill:#e0e0e0"
    surname = f"{patient['cognome']}^{patient['nome'].upper()}"
    overlay = (
        f'<text x="8" y="18" style="{text}">{HOSPITAL.upper()}</text>'
        f'<text x="8" y="34" style="{text}">{esc(surname)}</text>'
        f'<text x="8" y="50" style="{text}">ID {esc(study["patient"])}  {patient["sesso"]} {patient["eta"]}Y</text>'
        f'<text x="504" y="18" text-anchor="end" style="{text}">{modality} {"1.5T" if modality == "MR" else ""}</text>'
        f'<text x="504" y="34" text-anchor="end" style="{text}">{esc(study["data"][:10])}</text>'
        f'<text x="504" y="50" text-anchor="end" style="{text}">Ser {series}: {esc(label[:24])}</text>'
        f'<text x="504" y="66" text-anchor="end" style="{text}">Img {image}/{count}</text>'
        f'<text x="8" y="500" style="{text}">SL 6.0mm FOV 360mm</text>'
        f'<text x="20" y="262" style="{text}">R</text><text x="484" y="262" style="{text}">L</text>'
        f'<text x="256" y="474" text-anchor="middle" style="{text};fill:#ffd800">'
        "SYNTHETIC PHANTOM - NOT A REAL SCAN</text>"
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
        '<defs><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.85" '
        'numOctaves="2" seed="7"/><feColorMatrix type="saturate" values="0"/></filter></defs>'
        + "".join(shapes)
        + '<rect width="512" height="512" filter="url(#n)" opacity="0.13"/>'
        + overlay + "</svg>"
    )
    return svg.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "SanitaCartellaTraining"

    def log_message(self, format, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
                         "form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        query = params.get("q", "")[:64]
        parts = [part for part in url.path.split("/") if part]
        body, content_type = None, "text/html; charset=utf-8"
        if url.path == "/healthz":
            body, content_type = b'{"status":"ok"}', "application/json"
        elif url.path in {"/", "/index.html"}:
            body = worklist(query)
        elif len(parts) == 2 and parts[0] == "paziente":
            body = chart(parts[1], params.get("vista", ""), params.get("scheda", ""))
        elif parts == ["pacs"]:
            body = pacs_list(query)
        elif len(parts) == 3 and parts[:2] == ["pacs", "studio"]:
            body = viewer(parts[2], params.get("serie", ""), params.get("img", ""))
        elif len(parts) == 5 and parts[:2] == ["pacs", "img"] and parts[4].endswith(".svg"):
            series, image = parts[3], parts[4][:-4]
            if series.isdigit() and image.isdigit():
                body = synthetic_image(parts[2], int(series), int(image))
                content_type = "image/svg+xml"
        if body is None:
            self.send_error(404)
            return
        self._send(200, body, content_type)


def main() -> None:
    parser = argparse.ArgumentParser(description="Loopback synthetic EMR and PACS (training).")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Synthetic {PRODUCT} / {PACS_PRODUCT}: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
