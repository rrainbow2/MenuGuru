
import streamlit as st
import sqlite3
import fitz
import re
from datetime import datetime
from pathlib import Path
import pandas as pd

DB = Path(__file__).with_name("packing_slips.db")

def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        invoice TEXT,
        reference TEXT,
        airport TEXT,
        delivery_date TEXT,
        delivery_time TEXT,
        tail_reg TEXT,
        flight TEXT,
        status TEXT DEFAULT 'Not Started',
        source_text TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        qty REAL,
        item TEXT,
        notes TEXT,
        done INTEGER DEFAULT 0,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """)
    con.commit()
    con.close()

def pdf_text(uploaded_file):
    data = uploaded_file.read()
    doc = fitz.open(stream=data, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)

def first_match(pattern, text, flags=re.I|re.S, default=""):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else default

def clean_spaces(s):
    return re.sub(r"\s+", " ", s or "").strip()

def parse_job(text, filename):
    # Fields tuned to the Menu Guru packing slips supplied as examples.
    invoice = first_match(r"Invoice Number\s+([A-Z]+-\d+)", text)
    reference = first_match(r"Reference\s+(.+?)(?:\nBill to|\nThe Menu Guru)", text)
    reference = clean_spaces(reference)

    # Read the first catering-information line directly from the PDF text.
    # Example:
    # Catering Inflight - flight 4640018 - 9H-IFX iso 9H-XFX - London City, Jet Centre - 10th September 26 - 16:30LT -
    catering_line = ""
    for raw_line in text.splitlines():
        line = clean_spaces(raw_line)
        if line.lower().startswith("catering inflight"):
            catering_line = line
            break

    # Fallback for PDFs where PyMuPDF wraps the first catering line.
    if not catering_line:
        m = re.search(r"(Catering\s+Inflight.+?)(?:\n\d+(?:\.\d+)?\s*$)", text, re.I | re.S | re.M)
        if m:
            catering_line = clean_spaces(m.group(1))

    desc = catering_line

    airport = ""
    delivery_date = ""
    delivery_time = ""
    flight = ""
    tail = ""

    # Flight number from the first packing-information line.
    flight = first_match(r"(?:flight\s+)?(\d{5,})", desc)

    # Delivery date/time from that same first line.
    dt = re.search(
        r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{2,4})\s*-\s*(\d{1,2}:\d{2}\s*LT)",
        desc,
        re.I
    )
    if dt:
        delivery_date = clean_spaces(dt.group(1))
        delivery_time = clean_spaces(dt.group(2))

        # Everything between the previous " - " separator and the date is the airport/site.
        before_date = desc[:dt.start()].rstrip(" -")
        segments = [clean_spaces(x) for x in before_date.split(" - ") if clean_spaces(x)]
        if segments:
            airport = segments[-1]

    # If date/time were wrapped onto a second PDF text line, use a broader fallback.
    if not delivery_date or not delivery_time:
        m = re.search(
            r"Catering\s+Inflight\s*-\s*(.+?)\s*-\s*"
            r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{2,4})\s*-\s*"
            r"(\d{1,2}:\d{2}\s*LT)",
            text,
            re.I | re.S
        )
        if m:
            prefix = clean_spaces(m.group(1))
            delivery_date = clean_spaces(m.group(2))
            delivery_time = clean_spaces(m.group(3))
            segments = [clean_spaces(x) for x in prefix.split(" - ") if clean_spaces(x)]
            if segments:
                airport = segments[-1]

    # Tail registrations: common formats such as 9H-IFX, G-XXXX, N123AB
    tails = re.findall(r"\b(?:[A-Z0-9]{1,2}-[A-Z0-9]{3,5}|N\d{1,5}[A-Z]{0,2})\b", reference + " " + desc)
    # Avoid obvious invoice-like/date fragments
    seen = []
    for t in tails:
        if t not in seen:
            seen.append(t)
    tail = " / ".join(seen[:3])

    items = parse_items(text)
    return {
        "filename": filename,
        "invoice": invoice,
        "reference": reference,
        "airport": airport,
        "delivery_date": delivery_date,
        "delivery_time": delivery_time,
        "tail_reg": tail,
        "flight": flight,
        "status": "Not Started",
        "source_text": text,
        "items": items,
    }

def parse_items(text):
    """
    Parse Menu Guru packing-slip production rows.

    PyMuPDF commonly extracts the table header as:
        Description
        Quantity
    rather than "Description Quantity" on one line, so whitespace is
    deliberately flexible here.
    """
    m = re.search(r"Description\s+Quantity\s+(.+)", text, re.I | re.S)
    if not m:
        return []

    body = m.group(1)
    lines = [clean_spaces(x) for x in body.splitlines() if clean_spaces(x)]

    # Each real row ends with its quantity on a separate line in the supplied PDFs.
    chunks = []
    buf = []
    for line in lines:
        if re.fullmatch(r"\d+(?:\.\d+)?", line):
            if buf:
                chunks.append((" ".join(buf), float(line)))
                buf = []
        else:
            buf.append(line)

    results = []
    for content, qty in chunks:
        lower = content.lower()

        # These are job/header and delivery rows, not chef production items.
        if lower.startswith("catering inflight"):
            continue
        if lower.startswith("delivery charge"):
            continue
        if not content:
            continue

        item = content.strip()
        notes = ""

        # Move alerts / crew-specific instructions into the highlighted notes column.
        special_markers = [
            "***ALLERGY", "***DIETARY", "NB:", "crew 1:",
            "3 canapes -", "NO TOMATOES"
        ]
        positions = [
            lower.find(marker.lower())
            for marker in special_markers
            if lower.find(marker.lower()) >= 0
        ]
        if positions:
            idx = min(positions)
            if idx > 0:
                item = content[:idx].strip(" -;")
                notes = content[idx:].strip()

        results.append({
            "qty": qty,
            "item": item,
            "notes": notes
        })

    return results

def add_job(job):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO jobs(filename,invoice,reference,airport,delivery_date,delivery_time,tail_reg,flight,status,source_text)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        job["filename"], job["invoice"], job["reference"], job["airport"],
        job["delivery_date"], job["delivery_time"], job["tail_reg"], job["flight"],
        job["status"], job["source_text"]
    ))
    job_id = cur.lastrowid
    for it in job["items"]:
        cur.execute("INSERT INTO items(job_id,qty,item,notes,done) VALUES(?,?,?,?,0)",
                    (job_id, it["qty"], it["item"], it["notes"]))
    con.commit()
    con.close()
    return job_id

def get_jobs():
    con = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT j.*,
          COALESCE(SUM(i.done),0) AS done_count,
          COUNT(i.id) AS item_count
        FROM jobs j
        LEFT JOIN items i ON i.job_id=j.id
        GROUP BY j.id
        ORDER BY j.id DESC
    """, con)
    con.close()
    if not df.empty:
        df["progress"] = df.apply(
            lambda r: f"{int((r.done_count/r.item_count)*100)}%" if r.item_count else "0%", axis=1
        )
    return df

def get_items(job_id):
    con = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT * FROM items WHERE job_id=? ORDER BY id", con, params=(job_id,))
    con.close()
    return df

def update_item(item_id, done):
    con = sqlite3.connect(DB)
    con.execute("UPDATE items SET done=? WHERE id=?", (1 if done else 0, item_id))
    con.commit()
    con.close()

def update_status(job_id, status):
    con = sqlite3.connect(DB)
    con.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    con.commit()
    con.close()

def delete_job(job_id):
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM items WHERE job_id=?", (job_id,))
    con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    con.commit()
    con.close()

init_db()
st.set_page_config(page_title="Packing Slip Chef System", page_icon="🍽️", layout="wide")
st.title("🍽️ Packing Slip Chef System")
st.caption("Upload packing slips → review extracted job → chef checklist → live progress")

page = st.sidebar.radio("Go to", ["Upload packing slips", "Summary dashboard", "Chef checklist"])

if page == "Upload packing slips":
    st.subheader("Upload new packing slips")
    uploads = st.file_uploader("Choose PDF packing slips", type=["pdf"], accept_multiple_files=True)

    if uploads:
        for up in uploads:
            st.markdown(f"### {up.name}")
            try:
                text = pdf_text(up)
                job = parse_job(text, up.name)

                c1,c2,c3 = st.columns(3)
                job["reference"] = c1.text_input("Reference", job["reference"], key=f"ref_{up.name}")
                job["invoice"] = c2.text_input("Invoice", job["invoice"], key=f"inv_{up.name}")
                job["flight"] = c3.text_input("Flight", job["flight"], key=f"flight_{up.name}")

                c1,c2,c3,c4 = st.columns(4)
                job["airport"] = c1.text_input("Airport", job["airport"], key=f"airport_{up.name}")
                job["delivery_date"] = c2.text_input("Delivery date", job["delivery_date"], key=f"date_{up.name}")
                job["delivery_time"] = c3.text_input("Delivery time", job["delivery_time"], key=f"time_{up.name}")
                job["tail_reg"] = c4.text_input("Tail registration", job["tail_reg"], key=f"tail_{up.name}")

                st.caption("Airport, delivery date and time are read from the first Catering Inflight line of the packing slip.")

                st.write(f"**Extracted production items — {len(job['items'])} found**")
                edit_df = pd.DataFrame(job["items"])
                if edit_df.empty:
                    st.warning("No line items were detected. You can add them manually below.")
                    edit_df = pd.DataFrame([{"qty":1.0,"item":"","notes":""}])
                edited = st.data_editor(edit_df, num_rows="dynamic", use_container_width=True, key=f"items_{up.name}")

                if st.button(f"Add {up.name} to dashboard", key=f"add_{up.name}", type="primary"):
                    job["items"] = edited.fillna("").to_dict("records")
                    add_job(job)
                    st.success("Job added.")
            except Exception as e:
                st.error(f"Could not read this PDF: {e}")

elif page == "Summary dashboard":
    st.subheader("Live job summary")
    jobs = get_jobs()
    if jobs.empty:
        st.info("No jobs yet. Upload a packing slip first.")
    else:
        show = jobs[["id","status","reference","airport","delivery_date","delivery_time","tail_reg","invoice","progress"]].copy()
        show.columns = ["Job","Status","Reference","Airport","Delivery date","Time","Tail reg.","Invoice","Progress"]
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption("Use Chef checklist to open a job and tick off production items.")

elif page == "Chef checklist":
    jobs = get_jobs()
    if jobs.empty:
        st.info("No jobs yet. Upload a packing slip first.")
    else:
        labels = {
            int(r.id): f"#{int(r.id)} — {r.reference or r.invoice or r.filename}"
            for _, r in jobs.iterrows()
        }
        job_id = st.selectbox("Choose job", list(labels), format_func=lambda x: labels[x])
        row = jobs[jobs.id == job_id].iloc[0]

        st.subheader(row.reference or row.invoice)
        cols = st.columns(5)
        cols[0].metric("Airport", row.airport or "—")
        cols[1].metric("Delivery", row.delivery_date or "—")
        cols[2].metric("Time", row.delivery_time or "—")
        cols[3].metric("Tail", row.tail_reg or "—")
        cols[4].metric("Progress", row.progress)

        status = st.selectbox(
            "Job status",
            ["Not Started","In Prep","Complete","Dispatched"],
            index=["Not Started","In Prep","Complete","Dispatched"].index(row.status) if row.status in ["Not Started","In Prep","Complete","Dispatched"] else 0
        )
        if status != row.status:
            update_status(job_id, status)
            st.rerun()

        items = get_items(job_id)
        st.markdown("### Production checklist")
        if items.empty:
            st.warning("No production items were extracted for this job.")
        else:
            for _, it in items.iterrows():
                left, right = st.columns([1,9])
                done = left.checkbox("", bool(it.done), key=f"done_{int(it.id)}")
                if done != bool(it.done):
                    update_item(int(it.id), done)
                    st.rerun()

                qty = int(it.qty) if float(it.qty).is_integer() else it.qty
                right.markdown(f"**{qty} × {it['item']}**")
                if it.notes:
                    right.warning(it.notes)

        with st.expander("Original extracted PDF text"):
            st.text(row.source_text)

        st.divider()
        if st.button("Delete this job", type="secondary"):
            delete_job(job_id)
            st.rerun()
