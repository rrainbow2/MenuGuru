
# Packing Slip Chef System

This is a working local prototype designed around the Menu Guru packing-slip format supplied in the conversation.

## What it does

- Upload one or more packing-slip PDFs.
- Extract/reference job details such as reference, airport, delivery date/time, tail registration, invoice and flight number.
- Show the extracted values for review before saving.
- Create a live summary dashboard.
- Open a job as a chef production checklist.
- Tick individual items off as they are made.
- Track job status: Not Started, In Prep, Complete, Dispatched.
- Store data locally in SQLite.

## Run on Windows

1. Install Python 3.11 or newer.
2. Unzip this folder.
3. Open Command Prompt in the folder.
4. Run:

   pip install -r requirements.txt
   streamlit run app.py

5. Your browser will open the app.

## Run on Mac

Open Terminal in this folder and run:

   python3 -m pip install -r requirements.txt
   python3 -m streamlit run app.py

## Important

This version reads text-based PDFs like the two examples supplied. Scanned-image PDFs may require OCR in a later version.

The extraction rules are intentionally editable: after upload, the app shows the extracted values and line items before they are added to the dashboard.

For a multi-user kitchen deployment, the next step would be hosting this app on an internal/server/cloud environment and replacing the local SQLite file with a shared database.
