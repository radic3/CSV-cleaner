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
from flexible_parser import (
    is_channels_csv_flexible, 
    is_traffic_csv_flexible, 
    get_flexible_columns,
    analyze_csv_structure
)



app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")


# Ensure static files are served with proper headers for CSP
@app.after_request
def after_request(response):
    # Add basic CSP header that allows external scripts but blocks inline scripts
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';"
    return response

class StoredFile:
    def __init__(self, original_path: str, processed_path: str, processed_xlsx: Optional[str] = None):
        self.original_path = original_path
        self.processed_path = processed_path
        self.processed_xlsx = processed_xlsx
        self.file_type: Optional[str] = None  # 'channels' | 'traffic'
        self.split_done = False           # user has executed IT/EN split
        self.original_preview: Optional[pd.DataFrame] = None
        self.normalized = False           # user has normalized ArticleKey
        self.columns: Optional[list] = None  # Store the actual columns for this file


PROCESSED_FILES: dict[str, StoredFile] = {}
UPLOADED_TOKENS: list[str] = []  # Lista globale dei token caricati




def _get_channels_columns(content_bytes: bytes) -> list:
    """
    Ottieni le colonne effettive del file channels usando il parser elastico
    """
    try:
        return get_flexible_columns(content_bytes)
    except Exception:
        return ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]

def _is_channels_freeform_csv(content_bytes: bytes) -> bool:
    """
    Versione elastica del rilevamento file channels
    Si adatta automaticamente ai nomi delle colonne effettive
    """
    return is_channels_csv_flexible(content_bytes)


def _is_traffic_freeform_csv(content_bytes: bytes) -> bool:
    """
    Versione elastica del rilevamento file traffic
    Si adatta automaticamente ai nomi delle colonne effettive
    """
    return is_traffic_csv_flexible(content_bytes)




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
        
        # Get the actual columns from the dataframe
        categories = [col for col in df.columns if col != 'ArticleKey']
        
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

@app.route("/clear_session", methods=["POST"])
def clear_session():
    """Pulisce tutti i file caricati"""
    global UPLOADED_TOKENS
    
    # Pulisci i file temporanei
    for token in UPLOADED_TOKENS:
        stored = PROCESSED_FILES.get(token)
        if stored:
            try:
                if os.path.exists(stored.original_path):
                    os.unlink(stored.original_path)
                if os.path.exists(stored.processed_path):
                    os.unlink(stored.processed_path)
                if stored.processed_xlsx and os.path.exists(stored.processed_xlsx):
                    os.unlink(stored.processed_xlsx)
            except:
                pass
            # Rimuovi dal dizionario
            PROCESSED_FILES.pop(token, None)
    
    # Pulisci la lista globale
    UPLOADED_TOKENS = []
    
    flash("Sessione pulita. Tutti i file sono stati rimossi.")
    return redirect(url_for("index"))






@app.route("/process_all", methods=["POST"])
def process_all():
    """Process all uploaded files and show results with 4 tables"""
    tokens = request.form.getlist("tokens")
    
    # Se non ci sono token nel form, usa tutti quelli globali
    if not tokens:
        tokens = UPLOADED_TOKENS
    
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
                cols = stored.columns or ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
            elif stored.file_type == "traffic":
                df = parse_traffic(stored.original_path)
                cols = stored.columns or ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
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
                # Get columns from the first file of this type
                numeric_cols = None
                for token in tokens:
                    stored = PROCESSED_FILES.get(token)
                    if stored and stored.file_type == "channels" and stored.columns:
                        numeric_cols = stored.columns
                        break
                if not numeric_cols:
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

            # Just store the file, no processing needed for batch upload
            original_preview = None

            token = str(uuid.uuid4())
            # Create dummy processed path for compatibility
            proc_tmp = tempfile.NamedTemporaryFile(prefix="processed_", suffix=".csv", delete=False)
            proc_path = proc_tmp.name
            proc_tmp.close()

            st = StoredFile(original_path=orig_path, processed_path=proc_path, processed_xlsx=None)
            st.file_type = 'channels' if _is_channels_freeform_csv(content) else ('traffic' if _is_traffic_freeform_csv(content) else None)
            st.split_done = False
            st.original_preview = original_preview
            
            # Store the actual columns for this file
            if st.file_type == 'channels':
                st.columns = _get_channels_columns(content)
            elif st.file_type == 'traffic':
                st.columns = ["Entries","Exit Rate","Time Spent per Visit (seconds)","Unique Visitors","Page Views"]
            
            PROCESSED_FILES[token] = st
            
            # Aggiungi il token alla lista globale per mantenere i file caricati
            UPLOADED_TOKENS.append(token)

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
    
    # Crea un summary completo con tutti i file caricati (vecchi + nuovi)
    all_items = []
    for token in UPLOADED_TOKENS:
        stored = PROCESSED_FILES.get(token)
        if stored and os.path.exists(stored.original_path):
            filename = os.path.basename(stored.original_path)
            # Rimuovi il prefisso temporaneo per un nome più pulito
            if filename.startswith('original_'):
                filename = filename[9:]  # Rimuovi 'original_'
            all_items.append({
                "filename": filename,
                "type": stored.file_type or "unknown",
                "token": token,
                "status": "OK",
            })
    
    # Aggiungi eventuali errori dell'upload corrente
    all_items.extend([item for item in summary if item["status"] != "OK"])
    
    return render_template("confirm.html", items=all_items)




@app.route("/download_xlsx/<token>")
def download_xlsx(token: str):
    stored = PROCESSED_FILES.get(token)
    path = stored.processed_xlsx if stored else None
    if not path or not os.path.exists(path):
        flash("File XLSX non disponibile.")
        return redirect(url_for("index"))
    # Use generic filename since we don't know the type anymore
    fname = "processed_data.xlsx"
    return send_file(path, as_attachment=True, download_name=fname)





if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)


