
import pandas as pd
import numpy as np
import re
from pathlib import Path
from typing import Optional

def _read_text_lines(path):
    return Path(path).read_text(encoding="utf-8").splitlines()

def _normalize_key(path_str):
    s = (path_str or "").strip()
    if not s: 
        return s
    if s.startswith("/"):
        s = re.sub(r"/+$", "", s)
        s = re.sub(r"\.html?$", "", s)
    return s

def parse_traffic(csv_path: str) -> pd.DataFrame:
    """Parse Adobe Analytics Freeform for traffic (Entries, Exit Rate, Unique Visitors, Page Views)."""
    lines = _read_text_lines(csv_path)
    # locate the "Freeform table" header
    idx = next((i for i, ln in enumerate(lines) if "Freeform table" in ln), None)
    if idx is None:
        raise ValueError("Freeform table not found in traffic CSV.")
    header_i = next((i for i in range(idx+1, min(len(lines), idx+50))
                    if lines[i].startswith(",") and "Entries" in lines[i] and "Unique Visitors" in lines[i]), None)
    if header_i is None:
        raise ValueError("Traffic header not found.")
    headers = ["Page"] + [h.strip() for h in lines[header_i].split(",")[1:]]
    rows = []
    for ln in lines[header_i+1:]:
        if not ln.strip():
            break
        if ln.startswith(","):
            break
        parts = ln.split(",")
        if len(parts) < len(headers):
            if ln.strip().startswith("..."):
                break
            continue
        rows.append([parts[0]] + parts[1:len(headers)])
    df = pd.DataFrame(rows, columns=headers)
    # drop totals row
    df = df[df["Page"].ne("Page")]
    # numeric
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ArticleKey"] = df["Page"].apply(_normalize_key)
    df["lang"] = df["ArticleKey"].apply(lambda s: "IT" if str(s).startswith("/it/") else ("EN" if str(s).startswith("/en/") else "OTHER"))
    return df

def parse_channels(csv_path: str) -> pd.DataFrame:
    """Parse Adobe Analytics Freeform for acquisition channels (Page Views by channel)."""
    lines = _read_text_lines(csv_path)
    idx = next((i for i, ln in enumerate(lines) if "Freeform table" in ln), None)
    if idx is None:
        raise ValueError("Freeform table not found in channels CSV.")
    header1_i = next((i for i in range(idx+1, min(len(lines), idx+50))
                     if lines[i].startswith(",") and "Page Views" not in lines[i] and lines[i].count(",")>=4), None)
    if header1_i is None:
        raise ValueError("Channels header not found.")
    channels = [h.strip() for h in lines[header1_i].split(",")[1:]]
    start = header1_i + 2  # skip ",Page Views,..." line
    rows = []
    for ln in lines[start:]:
        if not ln.strip():
            break
        if ln.startswith(","):
            break
        parts = ln.split(",")
        if len(parts) < 1+len(channels):
            if ln.strip().startswith("..."):
                break
            continue
        rows.append([parts[0]] + parts[1:1+len(channels)])
    cols = ["Page"] + channels
    df = pd.DataFrame(rows, columns=cols)
    df = df[df["Page"].ne("Page")]
    for c in channels:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ArticleKey"] = df["Page"].apply(_normalize_key)
    df["lang"] = df["ArticleKey"].apply(lambda s: "IT" if str(s).startswith("/it/") else ("EN" if str(s).startswith("/en/") else "OTHER"))
    return df

def aggregate_traffic(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate duplicates (same ArticleKey) and compute weighted Exit Rate."""
    num_cols = ["Entries","Unique Visitors","Page Views"]
    agg = df.groupby("ArticleKey", as_index=False).agg(
        {**{c:"sum" for c in num_cols},
         **{"Exit Rate":"mean", "Time Spent per Visit (seconds)":"mean"}}
    )
    if "Exit Rate" in df.columns and "Page Views" in df.columns:
        tmp = df.copy()
        tmp["w"] = tmp["Page Views"].replace(0, np.nan)
        tmp["er_w"] = tmp["Exit Rate"] * tmp["w"]
        er = tmp.groupby("ArticleKey").apply(lambda g: np.nansum(g["er_w"])/np.nansum(g["w"]) if np.nansum(g["w"])>0 else np.nan)
        agg = agg.merge(er.rename("Exit Rate").reset_index(), on="ArticleKey", how="left", suffixes=("","_w"))
        agg["Exit Rate"] = agg["Exit Rate"].fillna(agg.pop("Exit Rate_w"))
    agg["lang"] = agg["ArticleKey"].apply(lambda s: "IT" if str(s).startswith("/it/") else ("EN" if str(s).startswith("/en/") else "OTHER"))
    return agg

def aggregate_channels(df: pd.DataFrame) -> pd.DataFrame:
    ch_cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
    agg = df.groupby("ArticleKey", as_index=False)[ch_cols].sum()
    agg["lang"] = agg["ArticleKey"].apply(lambda s: "IT" if str(s).startswith("/it/") else ("EN" if str(s).startswith("/en/") else "OTHER"))
    return agg

def write_templates(traf_agg: pd.DataFrame, chan_agg: pd.DataFrame, out_xlsx: str):
    def make_visit(df, lang):
        sub = df[df["lang"] == lang]
        cols = {"pagina": sub.get("Titolo", sub["ArticleKey"])}
        return pd.DataFrame({
            **cols,
            "visitatori unici": sub["Unique Visitors"].astype("Int64"),
            "visualizzazioni di pagina": sub["Page Views"].astype("Int64"),
        })
    def make_entries(df, lang):
        sub = df[df["lang"] == lang]
        cols = {"pagina": sub.get("Titolo", sub["ArticleKey"])}
        return pd.DataFrame({
            **cols,
            "Entries (volte in cui la pagina è stata la pagina di entrata sul sito)": sub["Entries"].astype("Int64"),
        })
    def make_exits(df, lang):
        sub = df[df["lang"] == lang]
        cols = {"pagina": sub.get("Titolo", sub["ArticleKey"])}
        return pd.DataFrame({
            **cols,
            "Exit Rate (% di volte in cui l'utente è uscito dopo aver visitato questa pagina)": sub["Exit Rate"],
        })
    def make_channels(df, lang):
        sub = df[df["lang"] == lang]
        ch_cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
        out = sub[["ArticleKey"]+ch_cols].copy()
        out["total"] = out[ch_cols].sum(axis=1).astype("Int64")
        for c in ch_cols:
            out[c] = out[c].astype("Int64")
        return out

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        make_visit(traf_agg,"IT").to_excel(writer, sheet_name="TEMPLATE VISIT E PAGEWEW ITA", index=False)
        make_visit(traf_agg,"EN").to_excel(writer, sheet_name="TEMPLATE VISIT E PAGEWEW EN", index=False)
        make_entries(traf_agg,"IT").to_excel(writer, sheet_name="TEMPLATE ENTRIES ITA", index=False)
        make_entries(traf_agg,"EN").to_excel(writer, sheet_name="TEMPLATE ENTRIES EN", index=False)
        make_exits(traf_agg,"IT").to_excel(writer, sheet_name="TEMPLATE EXITS ITA", index=False)
        make_exits(traf_agg,"EN").to_excel(writer, sheet_name="TEMPLATE EXITS EN", index=False)
        make_channels(chan_agg,"IT").to_excel(writer, sheet_name="INBIZ - canali di acquisizione ", index=False)
        make_channels(chan_agg,"EN").to_excel(writer, sheet_name="INBIZ - canali di acquisizi (EN", index=False)

def qc_against_ristrutturato(traf_agg, chan_agg, traf_ristr_xlsx=None, chan_ristr_xlsx=None):
    """Optional: compare with provided 'RISTRUTTURATO' files and return QC summary DataFrames."""
    qc = {}
    if traf_ristr_xlsx and Path(traf_ristr_xlsx).exists():
        tr = pd.read_excel(traf_ristr_xlsx)
        tr["ArticleKey"] = tr["ArticleKey"].apply(_normalize_key)
        cols = ["Entries","Exit Rate","Unique Visitors","Page Views"]
        merged = tr.merge(traf_agg[["ArticleKey"]+cols], on="ArticleKey", how="inner", suffixes=("_ristr","_py"))
        for m in cols:
            merged[f"delta_{m}"] = merged[f"{m}_py"] - merged[f"{m}_ristr"]
        qc["QC_TRAFFICO"] = merged
    if chan_ristr_xlsx and Path(chan_ristr_xlsx).exists():
        cr = pd.read_excel(chan_ristr_xlsx)
        cr["ArticleKey"] = cr["ArticleKey"].apply(_normalize_key)
        cols = ["Organic Search","Direct","Internal traffic","Referring Domains","Social Networks"]
        merged = cr.merge(chan_agg[["ArticleKey"]+cols], on="ArticleKey", how="inner", suffixes=("_ristr","_py"))
        for m in cols:
            merged[f"delta_{m}"] = merged[f"{m}_py"] - merged[f"{m}_ristr"]
        qc["QC_CANALI"] = merged
    return qc


def attach_titles(df: pd.DataFrame, lookup_csv: Optional[str]):
    if not lookup_csv:
        return df, None
    p = Path(lookup_csv)
    if not p.exists():
        return df, f"Lookup path not found: {lookup_csv}"
    lk = pd.read_csv(p, sep=None, engine="python", encoding="utf-8")
    # Expect columns: ArticleKey, Titolo (case-insensitive ok)
    cols = {c.lower(): c for c in lk.columns}
    if "articlekey" not in cols:
        return df, "Lookup CSV must contain 'ArticleKey' column"
    # normalize keys
    lk["ArticleKey_norm"] = lk[cols["articlekey"]].apply(_normalize_key)
    title_col = cols.get("titolo")
    if not title_col:
        # attempt to guess a title from last segment
        lk["Titolo"] = lk["ArticleKey_norm"].apply(lambda s: s.split("/")[-1].replace("-", " ").title() if isinstance(s,str) else s)
        title_col = "Titolo"
    else:
        lk = lk.rename(columns={title_col: "Titolo"})
    lk = lk[["ArticleKey_norm","Titolo"]].drop_duplicates()
    # attach
    merged = df.merge(lk, left_on="ArticleKey", right_on="ArticleKey_norm", how="left")
    merged.drop(columns=["ArticleKey_norm"], inplace=True)
    return merged, None

def run_pipeline(traffico_csv, canali_csv, out_xlsx, traf_ristr_xlsx=None, can_ristr_xlsx=None, lookup_csv=None):
    traf = parse_traffic(traffico_csv)
    chan = parse_channels(canali_csv)
    traf_agg = aggregate_traffic(traf)
    chan_agg = aggregate_channels(chan)
    traf_agg, err = attach_titles(traf_agg, lookup_csv)
    write_templates(traf_agg, chan_agg, out_xlsx)
    qc = qc_against_ristrutturato(traf_agg, chan_agg, traf_ristr_xlsx, can_ristr_xlsx)
    # If QC sheets exist, append them to the same workbook
    if qc:
        with pd.ExcelWriter(out_xlsx, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            for name, df in qc.items():
                df.to_excel(writer, sheet_name=name[:31], index=False)
    return out_xlsx

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Inbiz AA CSV -> Template Excel pipeline")
    ap.add_argument("--traffico", required=True, help="Percorso CSV RAW traffico")
    ap.add_argument("--canali", required=True, help="Percorso CSV RAW canali")
    ap.add_argument("--out", required=True, help="Output Excel")
    ap.add_argument("--traf_ristr", help="(Opzionale) XLSX traffico RISTRUTTURATO per QC")
    ap.add_argument("--can_ristr", help="(Opzionale) XLSX canali RISTRUTTURATO per QC")
    ap.add_argument("--lookup", help="(Opzionale) CSV con mapping ArticleKey -> Titolo (colonne: ArticleKey,Titolo)")
    args = ap.parse_args()
    run_pipeline(args.traffico, args.canali, args.out, args.traf_ristr, args.can_ristr, args.lookup)
