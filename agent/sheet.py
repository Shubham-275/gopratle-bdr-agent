"""Sheet storage. Two interchangeable backends with the same 3-method interface:

    rows()            -> [(row_id, {column: value}), ...]   (row_id = 1-based sheet row, header = 1)
    update(id, dict)  -> write the given columns on that row
    append(dict)      -> add a row, return its row_id

The Sheet is the single source of truth (status, follow-up due date, reply status),
so the agent is restart-safe and can run as a cron job or a long-lived worker.
"""
import csv
import os

from .config import get

COLUMNS = [
    "Company", "City",                      # <- the only two columns a human has to fill
    "Status", "Lead Name", "Role", "Lead Type", "Profile URL",
    "Email", "Email Confidence", "Pitch", "Other Leads",
    "Outreach Sent At", "Follow-up Due", "Follow-up Sent At",
    "Reply Status",                          # <- BDR types "replied" / "stop" to cancel follow-up
    "Source", "Requested By", "Notes",
]


class CsvSheet:
    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(path):
            self._write([])

    def rows(self):
        with open(self.path, newline="", encoding="utf-8") as f:
            return [(i + 2, {c: (r.get(c) or "") for c in COLUMNS}) for i, r in enumerate(csv.DictReader(f))]

    def update(self, row_id, values):
        rows = [r for _, r in self.rows()]
        rows[row_id - 2].update(values)
        self._write(rows)

    def append(self, values):
        rows = [r for _, r in self.rows()]
        rows.append({c: values.get(c, "") for c in COLUMNS})
        self._write(rows)
        return len(rows) + 1

    def _write(self, rows):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)


class GoogleSheet:
    def __init__(self, sheet_id: str, worksheet: str, creds_file: str):
        import gspread  # lazy: not needed for CSV/demo mode

        gc = gspread.service_account(filename=creds_file)
        sh = gc.open_by_key(sheet_id)
        try:
            self.ws = sh.worksheet(worksheet)
        except gspread.WorksheetNotFound:
            self.ws = sh.add_worksheet(worksheet, rows=1000, cols=len(COLUMNS))
        self._ensure_header()

    def _ensure_header(self):
        header = self.ws.row_values(1)
        if not header:
            header = COLUMNS[:]
        else:  # keep the user's column order, add any missing columns on the right
            header += [c for c in COLUMNS if c not in header]
        self.ws.update(range_name="A1", values=[header], value_input_option="RAW")
        self.header = header

    def rows(self):
        out = []
        for i, row in enumerate(self.ws.get_all_values()[1:], start=2):
            row = row + [""] * (len(self.header) - len(row))
            out.append((i, dict(zip(self.header, row))))
        return out

    def update(self, row_id, values):
        from gspread.utils import rowcol_to_a1

        data = [
            {"range": rowcol_to_a1(row_id, self.header.index(k) + 1), "values": [[v]]}
            for k, v in values.items() if k in self.header
        ]
        # RAW = scraped text is stored verbatim, never evaluated as a formula (no "=HYPERLINK(...)" injection)
        if data:
            self.ws.batch_update(data, value_input_option="RAW")

    def append(self, values):
        self.ws.append_row([values.get(c, "") for c in self.header], value_input_option="RAW")
        return len(self.ws.col_values(1))


def get_sheet():
    if get("SHEET_BACKEND", "csv").lower() == "google":
        return GoogleSheet(get("GOOGLE_SHEET_ID"), get("WORKSHEET", "Leads"), get("GOOGLE_CREDS_FILE", "service_account.json"))
    return CsvSheet(get("SHEET_CSV", "leads.csv"))
