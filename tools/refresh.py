#!/usr/bin/env python3
"""Mae Murray Foundation Halloween Raffle 2026: rebuild the patch data and the entries
spreadsheet from Stripe checkout sessions.

Usage:  python3 -I refresh.py OUT_DIR sessions1.json [sessions2.json ...]

Each sessions file is the JSON returned by Stripe's GET /v1/checkout/sessions
(status=complete, expand[]=data.line_items), or a plain list of session objects.
Writes into OUT_DIR:
  data.json                              the file the live patch reads (no personal data)
  entries.json                           every paid entry, in order of payment (PERSONAL DATA, keep private)
  Halloween_Raffle_2026_Entries.xlsx     the entries spreadsheet (PERSONAL DATA, keep private)
Prints a short summary and exits 0. Exit code 3 means a session could not be read.
"""
import json, sys, os, re, hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

TOTAL = 400          # pumpkins in the patch now
LEGACY_TOTAL = 100   # size of the patch when the first buyers were placed by shuffle; never change
SEED = 20261026      # shuffle seed; never change
# Payment intents that are MMF staff entries (highlighted in the spreadsheet, still real tickets)
STAFF_REFS = {"pi_3ULgPLKiKgGDHebJ1xqBkEhs": "MMF staff entry.",
              "pi_3ULlJrKiKgGDHebJ1UwCVs30": "MMF staff entry (kept after pumpkin-picking test, decided 2 Oct)."}
# Payment intents that have been refunded or voided: their tickets and pumpkins are released
VOID_REFS = set()
MAX_LABEL = 18

def load_sessions(paths):
    out = {}
    for p in paths:
        with open(p) as f:
            d = json.load(f)
        items = d["data"] if isinstance(d, dict) and "data" in d else d
        for s in items:
            if s.get("object") != "checkout.session": continue
            out[s["id"]] = s
    return list(out.values())

def field(s, key):
    for cf in s.get("custom_fields") or []:
        if cf.get("key") == key:
            t = cf.get("type")
            v = (cf.get(t) or {}).get("value")
            return v
    return None

def yesno(v):
    return {"yes": "Yes", "no": "No"}.get((v or "").lower(), "")

def entry_from(s):
    if s.get("status") != "complete" or s.get("payment_status") != "paid": return None
    cd = s.get("customer_details") or {}
    qty = None
    li = (s.get("line_items") or {}).get("data") or []
    if li: qty = sum(int(x.get("quantity") or 0) for x in li)
    if not qty:
        try: qty = int((s.get("metadata") or {}).get("tickets") or 0)
        except ValueError: qty = 0
    if not qty:
        qty = int(round((s.get("amount_total") or 0) / 500))
    if not qty:
        raise ValueError("cannot work out ticket quantity for " + s["id"])
    picks = [int(n) for n in re.findall(r"p(\d+)", s.get("client_reference_id") or "")]
    ref = s.get("payment_intent") or s["id"]
    note = STAFF_REFS.get(ref, "")
    if ref in VOID_REFS: note = ("VOID. " + note).strip()
    return dict(ts=s["created"], sid=hashlib.sha256(s["id"].encode()).hexdigest()[:16], name=(cd.get("name") or "").strip(), email=cd.get("email") or "",
                phone=cd.get("phone") or "", qty=qty, paid=(s.get("amount_total") or 0) / 100,
                over16=yesno(field(s, "ageconfirmation")), keep=yesno(field(s, "keepintouch")),
                ref=ref, source="Pumpkin patch" if (s.get("metadata") or {}).get("source") == "pumpkin_patch" else "Direct link",
                pumpkin=(field(s, "pumpkinname") or "").strip(), picks=picks, note=note,
                void=ref in VOID_REFS)

def rng(seed):
    s = seed
    def r():
        nonlocal s
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
        return s / 4294967296
    return r

def assign(entries):
    order = list(range(LEGACY_TOTAL)); r = rng(SEED)
    for j in range(LEGACY_TOTAL - 1, 0, -1):
        k = int(r() * (j + 1)); order[j], order[k] = order[k], order[j]
    assigned = {}; moved = []
    def label(x):
        nm = x["pumpkin"] or (x["name"].split()[0].capitalize() if x["name"] else "Picked")
        return nm[:MAX_LABEL]
    def nearest_free(i):
        for d in range(TOTAL):
            for c in (i - d, i + d):
                if 0 <= c < TOTAL and c not in assigned: return c
        return None
    legacy = [i for i in order] + [i for i in range(TOTAL) if i >= LEGACY_TOTAL]
    for x in entries:
        if x["void"]: continue
        picks = [p - 1 for p in x["picks"] if 1 <= p <= TOTAL][:x["qty"]]
        for q in range(x["qty"]):
            if q < len(picks):
                want = picks[q]
                if want in assigned:
                    got = nearest_free(want)
                    if got is not None: moved.append((label(x), want + 1, got + 1))
                else: got = want
            else:
                got = next((i for i in legacy if i not in assigned), None)
            if got is None: break
            assigned[got] = label(x)
    return assigned, moved

def sheet(entries, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.comments import Comment
    NAVY = "001E62"; PALE = "F4F7FB"; CREAM = "FFF6DD"
    F = lambda **k: Font(name="Arial", **k)
    thin = Side(style="thin", color="D0D7E2"); B = Border(top=thin, bottom=thin, left=thin, right=thin)
    wb = Workbook(); s = wb.active; s.title = "Summary"; s.sheet_view.showGridLines = False
    s.column_dimensions["A"].width = 34; s.column_dimensions["B"].width = 18; s.column_dimensions["C"].width = 60
    s["A1"] = "Mae Murray Foundation Halloween Raffle 2026"; s["A1"].font = F(bold=True, size=16, color=NAVY)
    s["A2"] = "Entries from the Stripe checkout. Draw: Monday 26 October 2026."; s["A2"].font = F(size=10, color="555555")
    s["A3"] = f"Last updated from Stripe: {datetime.now(ZoneInfo('Europe/London')).strftime('%d %b %Y, %H:%M')}"; s["A3"].font = F(size=10, color="555555")
    rows = [("Ticket price (£)", 5, "Set by Jilly. Change here if the price changes; amounts on Entries do not depend on it."),
            ("Number of purchases", "=COUNTA(Entries!B2:B1000)", ""),
            ("Tickets sold", "=SUM(Entries!E2:E1000)", ""),
            ("Total paid (£)", "=SUM(Entries!F2:F1000)", "Before Stripe fees."),
            ("Entries answering under 16", "=COUNTIF(Entries!I2:I1000,\"No\")", "Must be refunded. Under 16s cannot legally buy a ticket."),
            ("Happy to hear from MMF", "=COUNTIF(Entries!J2:J1000,\"Yes\")", "Only these people can be added to mailing lists."),
            ("Highest ticket number issued", "=IFERROR(MAX(Entries!H2:H1000),0)", "Draw a random number from 1 to this.")]
    for i, (a, b, c) in enumerate(rows, start=5):
        s[f"A{i}"] = a; s[f"B{i}"] = b; s[f"C{i}"] = c
        s[f"A{i}"].font = F(bold=True, color=NAVY); s[f"B{i}"].font = F(bold=True, size=12); s[f"C{i}"].font = F(size=9, color="555555")
        for col in "ABC": s[f"{col}{i}"].border = B; s[f"{col}{i}"].fill = PatternFill("solid", fgColor=PALE)
    s["B5"].font = F(bold=True, size=12, color="0000FF"); s["B5"].number_format = '£#,##0.00'
    s["B8"].number_format = '£#,##0.00'
    for r in (6, 7, 9, 10, 11): s[f"B{r}"].number_format = '0'
    s["A13"] = "How to use this"; s["A13"].font = F(bold=True, color=NAVY, size=12)
    notes = ["Each row on Entries is one purchase. Someone buying 5 tickets is one row with 5 in Tickets.",
             "Ticket numbers are given out automatically in order of purchase: First and Last show each buyer's run.",
             "Keep rows in date order and never delete one. If someone is refunded, mark them VOID in Notes so their numbers are not reused and nobody else moves.",
             "Pumpkin shows the name on the patch and which pumpkins they picked (blank means we placed them).",
             "Prize won and Winner contacted are for you to fill in on the day.",
             "This file holds personal details. Keep it in a restricted MMF folder and keep it 18 months for the council return."]
    for i, n in enumerate(notes, start=14):
        s[f"A{i}"] = f"• {n}"; s[f"A{i}"].font = F(size=10); s.merge_cells(f"A{i}:C{i}")
    e = wb.create_sheet("Entries")
    hdr = ["Date paid", "Name", "Email", "Phone", "Tickets", "Amount paid (£)", "First ticket no.", "Last ticket no.",
           "16 or over?", "Hear from MMF?", "Stripe payment ref", "Pumpkin", "Notes", "Prize won", "Winner contacted"]
    widths = [18, 22, 30, 16, 9, 15, 15, 15, 12, 15, 30, 24, 40, 12, 16]
    for c, (h, w) in enumerate(zip(hdr, widths), start=1):
        cell = e.cell(row=1, column=c, value=h)
        cell.font = F(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True); cell.border = B
        e.column_dimensions[cell.column_letter].width = w
    e.row_dimensions[1].height = 32
    for i, x in enumerate(entries, start=2):
        dt = datetime.fromtimestamp(x["ts"], ZoneInfo("Europe/London")).replace(tzinfo=None)
        pk = (x["pumpkin"] or "") + (" (" + ", ".join(str(p) for p in x["picks"]) + ")" if x["picks"] else "")
        vals = [dt, x["name"], x["email"], x["phone"], x["qty"], x["paid"],
                1 if i == 2 else f"=H{i-1}+1", f"=G{i}+E{i}-1", x["over16"], x["keep"], x["ref"], pk.strip(), x["note"], None, None]
        for c, v in enumerate(vals, start=1):
            cell = e.cell(row=i, column=c, value=v); cell.font = F(size=10); cell.border = B
            cell.alignment = Alignment(vertical="top", wrap_text=(c in (12, 13)))
        e.cell(row=i, column=1).number_format = "dd/mm/yyyy hh:mm"
        e.cell(row=i, column=6).number_format = '£#,##0.00'
        if x["note"].startswith("MMF staff"):
            for c in range(1, 16): e.cell(row=i, column=c).fill = PatternFill("solid", fgColor=CREAM)
    e["G2"].comment = Comment("Ticket numbering starts at 1. Each following row starts one after the previous buyer's last number.", "MMF")
    e.freeze_panes = "C2"; e.auto_filter.ref = f"A1:O{max(2, len(entries) + 1)}"
    dv1 = DataValidation(type="list", formula1='"1st,2nd,3rd"', allow_blank=True); dv2 = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    e.add_data_validation(dv1); e.add_data_validation(dv2); dv1.add("N2:N1000"); dv2.add("O2:O1000")
    wb.active = 1; wb.save(path)

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    sessions = load_sessions(sys.argv[2:])
    entries = []
    for s in sessions:
        try:
            e = entry_from(s)
        except Exception as ex:
            print("ERROR", ex); sys.exit(3)
        if e: entries.append(e)
    entries.sort(key=lambda x: (x["ts"], x["sid"]))  # same order as netlify/lib/patch.mjs
    assigned, moved = assign(entries)
    now = datetime.now(ZoneInfo("Europe/London")).strftime("%-d %B %Y, %H:%M")
    data = {"updated": now, "total": TOTAL, "assigned": {str(k): v for k, v in sorted(assigned.items())}}
    with open(os.path.join(out, "data.json"), "w") as f: json.dump(data, f, indent=1)
    with open(os.path.join(out, "entries.json"), "w") as f: json.dump(entries, f, indent=1)
    sheet(entries, os.path.join(out, "Halloween_Raffle_2026_Entries.xlsx"))
    sold = len(assigned); tickets = sum(x["qty"] for x in entries if not x["void"])
    print(f"{len(entries)} purchases, {tickets} tickets, {sold} of {TOTAL} pumpkins picked, £{tickets*5} taken")
    print("assigned:", data["assigned"])
    if moved: print("moved to nearest free pumpkin:", moved)

if __name__ == "__main__":
    main()
