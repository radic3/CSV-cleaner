import io
import os
import uuid
import tempfile
import re
from typing import Optional

import pandas as pd
  # Use non-interactive backend
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from csv_pipeline import parse_channels, parse_traffic

from url_title import extract_article_title


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

class StoredFile:
    def __init__(self, original_path: str, processed_path: str, processed_xlsx: Optional[str] = None):
        self.original_path = original_path
        self.processed_path = processed_path
        self.processed_xlsx = processed_xlsx
        self.file_type: Optional[str] = None  # 'channels' | 'traffic'
        self.split_done = False           # user has executed IT/EN split
        self.original_preview: Optional[pd.DataFrame] = None
        self.normalized = False           # user has normalized ArticleKey


PROCESSED_FILES: dict[str, StoredFile] = {}


def _detect_url_column(df: pd.DataFrame) -> Optional[str]:
    # Prefer exact 'Page' if present in any case
    for c in df.columns:
        if str(c).strip().lower() == "page":
            return c
    # Heuristic: choose object-like column with many URL/path-looking values
    best_col = None
    best_score = 0.0
    for c in df.columns:
        series = df[c].astype(str)
        sample = series.head(200)
        # Score: proportion of values that look like a path or URL
        looks_like = sample.str.match(r"^(https?://|/).+", na=False)
        score = looks_like.mean()
        # Boost if it's the first column
        if c == df.columns[0]:
            score += 0.05
        if score > best_score:
            best_score = score
            best_col = c
    # Require minimum confidence
    if best_score >= 0.3:
        return best_col
    return None


def _process_dataframe(df: pd.DataFrame, url_col: Optional[str]) -> tuple[pd.DataFrame, Optional[str]]:
    if url_col is None or url_col not in df.columns:
        return df, "Colonna URL non identificata in modo affidabile. Seleziona manualmente e riprova."
    out = df.copy()
    out["Titolo"] = out[url_col].apply(extract_article_title)
    return out, None


def _is_channels_freeform_csv(content_bytes: bytes) -> bool:
    try:
        text = content_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return False
    head_lines = [ln.strip() for ln in text.splitlines()[:80]]
    head = "\n".join(head_lines)
    required_tokens = [
        "Freeform table",
        "Organic Search",
        "Direct",
        "Internal traffic",
        "Referring Domains",
        "Social Networks",
    ]
    return all(any(tok in ln for ln in head_lines) if tok == "Freeform table" else (tok in head) for tok in required_tokens)


def _is_traffic_freeform_csv(content_bytes: bytes) -> bool:
    try:
        text = content_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return False
    head_lines = [ln.strip() for ln in text.splitlines()[:80]]
    head = "\n".join(head_lines)
    return (
        "Freeform table" in head
        and "Entries" in head
        and "Unique Visitors" in head
        and "Page Views" in head
    )


def _build_channels_xlsx_from_raw(csv_path: str) -> str:
    df = parse_channels(csv_path)
    ch_cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
    it = df[df["lang"] == "IT"][ ["ArticleKey"] + ch_cols ].copy()
    en = df[df["lang"] == "EN"][ ["ArticleKey"] + ch_cols ].copy()
    tmp = tempfile.NamedTemporaryFile(prefix="channels_", suffix=".xlsx", delete=False)
    xlsx_path = tmp.name
    tmp.close()
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        it.to_excel(writer, sheet_name="Articoli_IT", index=False)
        en.to_excel(writer, sheet_name="Articoli_EN", index=False)
    return xlsx_path


def _build_traffic_xlsx_from_raw(csv_path: str) -> str:
    df = parse_traffic(csv_path)
    cols = ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
    it = df[df["lang"] == "IT"][ ["ArticleKey"] + cols ].copy()
    en = df[df["lang"] == "EN"][ ["ArticleKey"] + cols ].copy()
    tmp = tempfile.NamedTemporaryFile(prefix="traffic_", suffix=".xlsx", delete=False)
    xlsx_path = tmp.name
    tmp.close()
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        it.to_excel(writer, sheet_name="Articoli_IT", index=False)
        en.to_excel(writer, sheet_name="Articoli_EN", index=False)
    return xlsx_path


def _normalize_articlekey_for_split(path: str) -> str:
    s = str(path or "").strip()
    s = re.sub(r"[?#].*$", "", s)
    s = re.sub(r"\\.html?$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"/+", "/", s)
    s = re.sub(r"^/(it|en)/", "/", s, flags=re.IGNORECASE)  # drop locale
    if not s.startswith("/"):
        s = "/" + s
    s = s.rstrip("/")
    return s.lower()


def _extract_name_from_key(path: str, capitalize_first: bool = False) -> str:
    s = str(path or "").strip()
    s = re.sub(r"[?#].*$", "", s)
    s = re.sub(r"/+", "/", s)
    # take last segment only
    s = s.rstrip("/")
    seg = s.split("/")[-1]
    seg = re.sub(r"\.html?$", "", seg, flags=re.IGNORECASE)
    seg = seg.replace("_", "-")
    seg = re.sub(r"-+", " ", seg)
    seg = re.sub(r"[\(\)\[\]{}\.,;:!\?\"']+", " ", seg)
    seg = re.sub(r"\s+", " ", seg).strip()
    if capitalize_first and seg:
        seg = seg[0].upper() + seg[1:]
    return seg


def _add_excel_charts_to_sheet(worksheet, df: pd.DataFrame, lang: str):
    """Add native Excel charts to worksheet"""
    try:
        if df.empty:
            return
        
        # Remove sum row for charts
        chart_df = df.copy()
        if not chart_df.empty and chart_df.iloc[-1]["ArticleKey"] == "TOTALE":
            chart_df = chart_df.iloc[:-1]
        
        if chart_df.empty:
            return
        
        from openpyxl.chart import PieChart, BarChart, Reference
        
        categories = ['Organic Search', 'Direct', 'Internal traffic', 'Referring Domains', 'Social Networks']
        
        # 1. Pie Chart - Sum of each category
        pie_sums = chart_df[categories].sum()
        
        # Create pie chart
        pie_chart = PieChart()
        pie_chart.title = f"Distribuzione Canali - {lang}"
        pie_chart.height = 10
        pie_chart.width = 15
        
        # Use the TOTALE row data for pie chart (if it exists)
        total_row = None
        for i, row in enumerate(chart_df.values):
            if len(row) > 0 and str(row[0]) == "TOTALE":
                total_row = i + 2  # +2 because pandas is 0-indexed and we have header
                break
        
        if total_row:
            # Use existing TOTALE row data
            pie_data = Reference(worksheet, min_col=2, min_row=total_row, max_col=6, max_row=total_row)
            pie_labels = Reference(worksheet, min_col=2, min_row=1, max_col=6, max_row=1)  # Use header row for labels
        else:
            # Fallback: create summary data in a separate area
            summary_start_row = len(chart_df) + 5  # Start well after data
            for i, category in enumerate(categories):
                worksheet.cell(row=summary_start_row + i, column=1, value=category)
                worksheet.cell(row=summary_start_row + i, column=2, value=float(pie_sums[category]))
            
            pie_data = Reference(worksheet, min_col=2, min_row=summary_start_row, max_col=2, max_row=summary_start_row + len(categories) - 1)
            pie_labels = Reference(worksheet, min_col=1, min_row=summary_start_row, max_col=1, max_row=summary_start_row + len(categories) - 1)
        
        pie_chart.add_data(pie_data, titles_from_data=False)
        pie_chart.set_categories(pie_labels)
        
        # Position pie chart
        worksheet.add_chart(pie_chart, "H2")
        
        # 2. Bar Chart - Individual values for each article
        bar_chart = BarChart()
        bar_chart.type = "col"
        bar_chart.style = 10
        bar_chart.title = f"Confronto Canali per Articolo - {lang}"
        bar_chart.y_axis.title = 'Valori'
        bar_chart.x_axis.title = 'Articoli'
        bar_chart.height = 10
        bar_chart.width = 20
        
        # Set categories (article names)
        data_start_row = 2  # Skip header
        data_end_row = len(chart_df) + 1
        labels = Reference(worksheet, min_col=1, min_row=data_start_row, max_col=1, max_row=data_end_row)
        bar_chart.set_categories(labels)
        
        # Add data series for each category
        for i, category in enumerate(categories):
            data = Reference(worksheet, min_col=2+i, min_row=data_start_row, max_col=2+i, max_row=data_end_row)
            series = bar_chart.add_data(data, titles_from_data=False)
            if series:
                series.title = category
        
        # Position bar chart
        worksheet.add_chart(bar_chart, "H20")
        
    except Exception as e:
        # If chart creation fails, just continue without charts
        print(f"Chart creation failed: {e}")
        pass

def _add_traffic_charts_to_sheet(worksheet, df: pd.DataFrame, lang: str):
    """Add charts for traffic data"""
    try:
        if df.empty:
            return
        
        # Remove sum row for charts
        chart_df = df.copy()
        if not chart_df.empty and chart_df.iloc[-1]["ArticleKey"] == "TOTALE":
            chart_df = chart_df.iloc[:-1]
        
        if chart_df.empty:
            return
        
        from openpyxl.chart import BarChart, Reference
        
        # Get numeric columns (exclude ArticleKey)
        numeric_cols = [col for col in chart_df.columns if col != 'ArticleKey']
        
        if len(numeric_cols) == 0:
            return
        
        # Create bar chart for traffic data
        bar_chart = BarChart()
        bar_chart.type = "col"
        bar_chart.style = 10
        bar_chart.title = f"Traffico per Articolo - {lang}"
        bar_chart.y_axis.title = 'Valori'
        bar_chart.x_axis.title = 'Articoli'
        bar_chart.height = 10
        bar_chart.width = 20
        
        # Set categories (article names)
        data_start_row = 2
        data_end_row = len(chart_df) + 1
        labels = Reference(worksheet, min_col=1, min_row=data_start_row, max_col=1, max_row=data_end_row)
        bar_chart.set_categories(labels)
        
        # Add data series for each numeric column
        for i, col in enumerate(numeric_cols):
            data = Reference(worksheet, min_col=2+i, min_row=data_start_row, max_col=2+i, max_row=data_end_row)
            series = bar_chart.add_data(data, titles_from_data=False)
            if series:
                series.title = col
        
        # Position bar chart
        worksheet.add_chart(bar_chart, "H2")
        
    except Exception as e:
        print(f"Traffic chart creation failed: {e}")
        pass

def _add_sum_row_to_dataframe(df: pd.DataFrame, numeric_cols: list) -> pd.DataFrame:
    """Add a sum row to dataframe for numeric columns"""
    if df.empty:
        return df
    
    # Create sum row
    sum_row = {}
    for col in df.columns:
        if col in numeric_cols:
            sum_row[col] = df[col].sum()
        else:
            sum_row[col] = "TOTALE" if col == "ArticleKey" else ""
    
    # Add sum row
    sum_df = pd.DataFrame([sum_row])
    return pd.concat([df, sum_df], ignore_index=True)


@app.route("/", methods=["GET"]) 
def index():
    return render_template("upload.html")


@app.route("/process", methods=["POST"]) 
def process():
    file = request.files.get("file")
    if not file:
        flash("Seleziona o trascina un file CSV.")
        return redirect(url_for("index"))
    try:
        content = file.read()
        # Persist original upload immediately for downstream parsing
        orig_tmp = tempfile.NamedTemporaryFile(prefix="original_", suffix=".csv", delete=False)
        orig_path = orig_tmp.name
        orig_tmp.write(content)
        orig_tmp.flush()
        orig_tmp.close()

        # If it's a Channels/Traffic Freeform CSV, build XLSX later on split
        xlsx_path = None
        if _is_channels_freeform_csv(content) or _is_traffic_freeform_csv(content):
            xlsx_path = None

        # Also load into pandas for preview/URL extraction flows
        df = pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding="utf-8")
    except Exception as e:
        flash(f"Errore nella lettura del CSV: {e}")
        return redirect(url_for("index"))

    url_col = _detect_url_column(df)
    # Build initial preview of the ORIGINAL upload (no split yet)
    processed, err = _process_dataframe(df, url_col)
    original_preview = df.head(100)
    is_channels = _is_channels_freeform_csv(content)
    is_traffic = _is_traffic_freeform_csv(content)
    it_rows = en_rows = None
    csv_df = processed  # placeholder; not shown until split

    # persist original and processed for later reprocessing
    token = str(uuid.uuid4())
    proc_tmp = tempfile.NamedTemporaryFile(prefix="processed_", suffix=".csv", delete=False)
    proc_path = proc_tmp.name
    proc_tmp.close()
    csv_df.to_csv(proc_path, index=False)
    st = StoredFile(original_path=orig_path, processed_path=proc_path, processed_xlsx=xlsx_path)
    st.file_type = 'channels' if is_channels else ('traffic' if is_traffic else None)
    st.split_done = False
    st.original_preview = original_preview
    PROCESSED_FILES[token] = st

    # prepare preview
    preview_rows = processed.head(100).to_dict(orient="records")
    return render_template(
        "preview.html",
        columns=list(processed.columns),
        rows=preview_rows,
        token=token,
        detected_col=url_col,
        warning=err,
        is_channels=is_channels,
        is_traffic=is_traffic,
        split_done=False,
        orig_columns=list(original_preview.columns),
        orig_rows=original_preview.to_dict(orient="records"),
    )


@app.route("/preview/<token>")
def preview_token(token: str):
    stored = PROCESSED_FILES.get(token)
    if not stored or not os.path.exists(stored.original_path):
        flash("Sessione non trovata.")
        return redirect(url_for("index"))
    
    # No batch tracking in simplified flow
    batch_token = None
    
    # Render original preview state
    orig = stored.original_preview if stored.original_preview is not None else pd.read_csv(
        stored.original_path, sep=None, engine="python", encoding="utf-8", on_bad_lines="skip"
    ).head(100)
    return render_template(
        "preview.html",
        columns=["Titolo"],  # hidden in this path; page expects columns variable
        rows=[],
        token=token,
        detected_col=None,
        warning=None,
        is_channels=(stored.file_type == 'channels'),
        is_traffic=(stored.file_type == 'traffic'),
        split_done=stored.split_done,
        orig_columns=list(orig.columns),
        orig_rows=orig.to_dict(orient="records"),
        batch_token=batch_token,
    )


@app.route("/process_all", methods=["POST"])
def process_all():
    """Process all uploaded files and show results with 4 tables"""
    tokens = request.form.getlist("tokens")
    if not tokens:
        flash("Nessun file da elaborare.")
        return redirect(url_for("index"))
    
    # Process all files and collect data
    results = {
        "channels_it": [],
        "channels_en": [],
        "traffic_it": [],
        "traffic_en": [],
    }
    
    original_counts = {"channels": 0, "traffic": 0}
    
    for token in tokens:
        stored = PROCESSED_FILES.get(token)
        if not stored or not os.path.exists(stored.original_path):
            continue
            
        try:
            # Count original rows
            orig_df = pd.read_csv(stored.original_path, sep=None, engine="python", encoding="utf-8", on_bad_lines="skip")
            original_counts[stored.file_type] += len(orig_df)
            
            # Process based on file type
            if stored.file_type == "channels":
                df = parse_channels(stored.original_path)
                cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
            elif stored.file_type == "traffic":
                df = parse_traffic(stored.original_path)
                cols = ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
            else:
                continue
                
            # Split and normalize
            it_df = df[df["lang"] == "IT"][ ["ArticleKey"] + cols ].copy()
            en_df = df[df["lang"] == "EN"][ ["ArticleKey"] + cols ].copy()
            
            # Normalize ArticleKey
            for d in (it_df, en_df):
                d["ArticleKey"] = d["ArticleKey"].apply(_normalize_articlekey_for_split)
                d["ArticleKey"] = d["ArticleKey"].apply(lambda p: _extract_name_from_key(p, capitalize_first=True))
            
            # Store results
            if stored.file_type == "channels":
                results["channels_it"].append(it_df)
                results["channels_en"].append(en_df)
            else:
                results["traffic_it"].append(it_df)
                results["traffic_en"].append(en_df)
                
        except Exception as e:
            flash(f"Errore nell'elaborazione di {os.path.basename(stored.original_path)}: {e}")
            continue
    
    # Concatenate results and add sum rows
    final_results = {}
    for key, dfs in results.items():
        if dfs:
            df = pd.concat(dfs, ignore_index=True)
            # Add sum row for channels data
            if "channels" in key:
                numeric_cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
                df = _add_sum_row_to_dataframe(df, numeric_cols)
            elif "traffic" in key:
                numeric_cols = ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
                df = _add_sum_row_to_dataframe(df, numeric_cols)
            final_results[key] = df
        else:
            final_results[key] = pd.DataFrame()
    
    # Charts are now only in XLSX files, no web charts needed

    # Generate XLSX files
    xlsx_links = {}
    
    # Channels XLSX
    if not final_results["channels_it"].empty or not final_results["channels_en"].empty:
        tmp = tempfile.NamedTemporaryFile(prefix="Channels_", suffix=".xlsx", delete=False)
        p = tmp.name; tmp.close()
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            if not final_results["channels_it"].empty:
                final_results["channels_it"].to_excel(w, sheet_name="Articoli_IT", index=False)
                # Add native Excel charts to IT sheet
                _add_excel_charts_to_sheet(w.sheets["Articoli_IT"], final_results["channels_it"], "IT")
            
            if not final_results["channels_en"].empty:
                final_results["channels_en"].to_excel(w, sheet_name="Articoli_EN", index=False)
                # Add native Excel charts to EN sheet
                _add_excel_charts_to_sheet(w.sheets["Articoli_EN"], final_results["channels_en"], "EN")
        token_x = str(uuid.uuid4())
        PROCESSED_FILES[token_x] = StoredFile(p, p, p)
        xlsx_links["channels"] = url_for("download_xlsx", token=token_x)
    
    # Traffic XLSX
    if not final_results["traffic_it"].empty or not final_results["traffic_en"].empty:
        tmp = tempfile.NamedTemporaryFile(prefix="Traffic_", suffix=".xlsx", delete=False)
        p = tmp.name; tmp.close()
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            if not final_results["traffic_it"].empty:
                final_results["traffic_it"].to_excel(w, sheet_name="Articoli_IT", index=False)
                _add_traffic_charts_to_sheet(w.sheets["Articoli_IT"], final_results["traffic_it"], "IT")
            if not final_results["traffic_en"].empty:
                final_results["traffic_en"].to_excel(w, sheet_name="Articoli_EN", index=False)
                _add_traffic_charts_to_sheet(w.sheets["Articoli_EN"], final_results["traffic_en"], "EN")
        token_x = str(uuid.uuid4())
        PROCESSED_FILES[token_x] = StoredFile(p, p, p)
        xlsx_links["traffic"] = url_for("download_xlsx", token=token_x)
    
    # Combined XLSX
    if (not final_results["channels_it"].empty or not final_results["channels_en"].empty) and \
       (not final_results["traffic_it"].empty or not final_results["traffic_en"].empty):
        tmp = tempfile.NamedTemporaryFile(prefix="Combined_", suffix=".xlsx", delete=False)
        p = tmp.name; tmp.close()
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            if not final_results["channels_it"].empty:
                final_results["channels_it"].to_excel(w, sheet_name="Canali_IT", index=False)
                _add_excel_charts_to_sheet(w.sheets["Canali_IT"], final_results["channels_it"], "IT")
            if not final_results["channels_en"].empty:
                final_results["channels_en"].to_excel(w, sheet_name="Canali_EN", index=False)
                _add_excel_charts_to_sheet(w.sheets["Canali_EN"], final_results["channels_en"], "EN")
            if not final_results["traffic_it"].empty:
                final_results["traffic_it"].to_excel(w, sheet_name="Traffico_IT", index=False)
                _add_traffic_charts_to_sheet(w.sheets["Traffico_IT"], final_results["traffic_it"], "IT")
            if not final_results["traffic_en"].empty:
                final_results["traffic_en"].to_excel(w, sheet_name="Traffico_EN", index=False)
                _add_traffic_charts_to_sheet(w.sheets["Traffico_EN"], final_results["traffic_en"], "EN")
        token_x = str(uuid.uuid4())
        PROCESSED_FILES[token_x] = StoredFile(p, p, p)
        xlsx_links["combined"] = url_for("download_xlsx", token=token_x)
    
    return render_template("results.html", 
                         results=final_results,
                         original_counts=original_counts,
                         xlsx_links=xlsx_links)

@app.route("/process_batch_run", methods=["POST"]) 
def process_batch_run():
    tokens = request.form.getlist("tokens")
    if not tokens:
        flash("Nessun file da elaborare.")
        return redirect(url_for("index"))
    merged = {
        "channels": {"IT": [], "EN": []},
        "traffic": {"IT": [], "EN": []},
    }
    for t in tokens:
        st = PROCESSED_FILES.get(t)
        if not st or not os.path.exists(st.original_path) or st.file_type not in {"channels","traffic"}:
            continue
        try:
            if st.file_type == "channels":
                df = parse_channels(st.original_path)
                cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
            else:
                df = parse_traffic(st.original_path)
                cols = ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
            it_df = df[df["lang"] == "IT"][ ["ArticleKey"] + cols ].copy()
            en_df = df[df["lang"] == "EN"][ ["ArticleKey"] + cols ].copy()
            # normalize and reduce ArticleKey to extracted name
            for d in (it_df, en_df):
                d["ArticleKey"] = d["ArticleKey"].apply(_normalize_articlekey_for_split)
                d["ArticleKey"] = d["ArticleKey"].apply(lambda p: _extract_name_from_key(p, capitalize_first=True))
            merged[st.file_type]["IT"].append(it_df)
            merged[st.file_type]["EN"].append(en_df)
        except Exception:
            continue
    # concat and render summary page with links to XLSX builds
    outputs = {}
    for typ in ("channels","traffic"):
        for lang in ("IT","EN"):
            lst = merged[typ][lang]
            if lst:
                outputs[(typ, lang)] = pd.concat(lst, ignore_index=True)
    # Build XLSX files for each type present
    links = {}
    if any(k[0]=="channels" for k in outputs.keys()):
        it = outputs.get(("channels","IT"), pd.DataFrame())
        en = outputs.get(("channels","EN"), pd.DataFrame())
        tmp = tempfile.NamedTemporaryFile(prefix="channels_batch_", suffix=".xlsx", delete=False)
        p = tmp.name; tmp.close()
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            if not it.empty: it.to_excel(w, sheet_name="Articoli_IT", index=False)
            if not en.empty: en.to_excel(w, sheet_name="Articoli_EN", index=False)
        token_x = str(uuid.uuid4()); PROCESSED_FILES[token_x] = StoredFile(p, p, p)
        links["channels_xlsx"] = url_for("download_xlsx", token=token_x)
    if any(k[0]=="traffic" for k in outputs.keys()):
        it = outputs.get(("traffic","IT"), pd.DataFrame())
        en = outputs.get(("traffic","EN"), pd.DataFrame())
        tmp = tempfile.NamedTemporaryFile(prefix="traffic_batch_", suffix=".xlsx", delete=False)
        p = tmp.name; tmp.close()
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            if not it.empty: it.to_excel(w, sheet_name="Articoli_IT", index=False)
            if not en.empty: en.to_excel(w, sheet_name="Articoli_EN", index=False)
        token_x = str(uuid.uuid4()); PROCESSED_FILES[token_x] = StoredFile(p, p, p)
        links["traffic_xlsx"] = url_for("download_xlsx", token=token_x)
    
    # Build combined XLSX with both channels and traffic
    if any(k[0]=="channels" for k in outputs.keys()) and any(k[0]=="traffic" for k in outputs.keys()):
        tmp = tempfile.NamedTemporaryFile(prefix="combined_batch_", suffix=".xlsx", delete=False)
        p = tmp.name; tmp.close()
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            # Channels sheets
            ch_it = outputs.get(("channels","IT"), pd.DataFrame())
            ch_en = outputs.get(("channels","EN"), pd.DataFrame())
            if not ch_it.empty: ch_it.to_excel(w, sheet_name="Canali_IT", index=False)
            if not ch_en.empty: ch_en.to_excel(w, sheet_name="Canali_EN", index=False)
            # Traffic sheets
            tr_it = outputs.get(("traffic","IT"), pd.DataFrame())
            tr_en = outputs.get(("traffic","EN"), pd.DataFrame())
            if not tr_it.empty: tr_it.to_excel(w, sheet_name="Traffico_IT", index=False)
            if not tr_en.empty: tr_en.to_excel(w, sheet_name="Traffico_EN", index=False)
        token_x = str(uuid.uuid4()); PROCESSED_FILES[token_x] = StoredFile(p, p, p)
        links["combined_xlsx"] = url_for("download_xlsx", token=token_x)
    return render_template("batch_run.html", links=links, outputs_meta=[(k[0],k[1], len(v)) for k,v in outputs.items()], batch_token=request.form.get("batch_token", ""))
@app.route("/process_batch", methods=["POST"]) 
def process_batch():
    files = request.files.getlist("files")
    if not files:
        flash("Seleziona o trascina uno o più file CSV.")
        return redirect(url_for("index"))
    summary = []
    for f in files:
        try:
            content = f.read()
            orig_tmp = tempfile.NamedTemporaryFile(prefix="original_", suffix=".csv", delete=False)
            orig_path = orig_tmp.name
            orig_tmp.write(content)
            orig_tmp.flush(); orig_tmp.close()

            df = pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding="utf-8")
            url_col = _detect_url_column(df)
            processed, err = _process_dataframe(df, url_col)
            original_preview = df.head(100)

            token = str(uuid.uuid4())
            proc_tmp = tempfile.NamedTemporaryFile(prefix="processed_", suffix=".csv", delete=False)
            proc_path = proc_tmp.name
            proc_tmp.close()
            processed.to_csv(proc_path, index=False)

            st = StoredFile(original_path=orig_path, processed_path=proc_path, processed_xlsx=None)
            st.file_type = 'channels' if _is_channels_freeform_csv(content) else ('traffic' if _is_traffic_freeform_csv(content) else None)
            st.split_done = False
            st.original_preview = original_preview
            PROCESSED_FILES[token] = st

            summary.append({
                "filename": f.filename,
                "type": st.file_type or "unknown",
                "token": token,
                "status": "OK",
            })
        except Exception as e:
            summary.append({
                "filename": getattr(f, 'filename', 'sconosciuto'),
                "type": "error",
                "token": None,
                "status": f"Errore: {e}",
            })
    return render_template("confirm.html", items=summary)


@app.route("/download/<token>")
def download(token: str):
    stored = PROCESSED_FILES.get(token)
    path = stored.processed_path if stored else None
    if not path or not os.path.exists(path):
        flash("File non trovato o scaduto.")
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True, download_name="processed_data.csv")


@app.route("/download_xlsx/<token>")
def download_xlsx(token: str):
    stored = PROCESSED_FILES.get(token)
    path = stored.processed_xlsx if stored else None
    if (not path or not os.path.exists(path)) and stored and stored.file_type in {"channels","traffic"}:
        # build on-demand if detection failed earlier
        path = _build_channels_xlsx_from_raw(stored.original_path) if stored.file_type == 'channels' else _build_traffic_xlsx_from_raw(stored.original_path)
        stored.processed_xlsx = path
    if not path or not os.path.exists(path):
        flash("File XLSX non disponibile per questo upload.")
        return redirect(url_for("index"))
    fname = "channels_ristrutturato.xlsx" if stored and stored.file_type == 'channels' else "traffic_ristrutturato.xlsx"
    return send_file(path, as_attachment=True, download_name=fname)



@app.route("/reprocess", methods=["POST"]) 
def reprocess():
    token = request.form.get("token")
    action = request.form.get("action")
    col = request.form.get("url_col")
    stored = PROCESSED_FILES.get(token)
    if not stored or not os.path.exists(stored.original_path):
        flash("Sessione scaduta, ricarica il CSV.")
        return redirect(url_for("index"))
    if stored and stored.file_type in {"channels","traffic"} and (action == "split" or action == "normalize" or stored.split_done):
        # Rebuild split preview; column selection not needed
        try:
            if stored.file_type == 'channels':
                df_parsed = parse_channels(stored.original_path)
                cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
            else:
                df_parsed = parse_traffic(stored.original_path)
                cols = ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
        except Exception as e:
            flash(f"Separazione IT/EN fallita: {e}")
            return redirect(url_for("index"))
        it_df = df_parsed[df_parsed["lang"] == "IT"][ ["ArticleKey"] + cols ].copy()
        en_df = df_parsed[df_parsed["lang"] == "EN"][ ["ArticleKey"] + cols ].copy()
        split_done = True
        # Optional normalization of ArticleKey after split
        if action == "normalize" or stored.normalized:
            it_df["ArticleKey"] = it_df["ArticleKey"].apply(_normalize_articlekey_for_split)
            en_df["ArticleKey"] = en_df["ArticleKey"].apply(_normalize_articlekey_for_split)
            it_df["ArticleKey"] = it_df["ArticleKey"].apply(lambda p: _extract_name_from_key(p, capitalize_first=True))
            en_df["ArticleKey"] = en_df["ArticleKey"].apply(lambda p: _extract_name_from_key(p, capitalize_first=True))
            stored.normalized = True
        # update processed CSV (concatenated with lang)
        csv_df = pd.concat([
            it_df.assign(lang="IT"),
            en_df.assign(lang="EN"),
        ], ignore_index=True)
        csv_df.to_csv(stored.processed_path, index=False)
        # build XLSX on first split
        if not stored.processed_xlsx:
            stored.processed_xlsx = _build_channels_xlsx_from_raw(stored.original_path) if stored.file_type == 'channels' else _build_traffic_xlsx_from_raw(stored.original_path)
        stored.split_done = True
        # No batch tracking in simplified flow
        batch_token = None
        
        return render_template(
            "preview.html",
            is_channels=(stored.file_type == 'channels'),
            is_traffic=(stored.file_type == 'traffic'),
            split_done=split_done,
            it_columns=list(it_df.columns),
            en_columns=list(en_df.columns),
            it_rows=it_df.head(100).to_dict(orient="records"),
            en_rows=en_df.head(100).to_dict(orient="records"),
            token=token,
            detected_col=None,
            warning=None,
            batch_token=batch_token,
        )
    else:
        try:
            df = pd.read_csv(
                stored.original_path,
                sep=None,
                engine="python",
                encoding="utf-8",
                on_bad_lines="skip",
            )
        except Exception as e:
            flash(f"Errore nella rilettura del CSV originale: {e}")
            return redirect(url_for("index"))
        processed, err = _process_dataframe(df, col)
        processed.to_csv(stored.processed_path, index=False)
        preview_rows = processed.head(100).to_dict(orient="records")
        return render_template(
            "preview.html",
            columns=list(processed.columns),
            rows=preview_rows,
            token=token,
            detected_col=col,
            warning=err,
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="127.0.0.1", port=port, debug=True)


