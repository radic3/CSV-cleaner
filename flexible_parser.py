#!/usr/bin/env python3
"""
Parser elastico per file CSV di Adobe Analytics
Analizza la struttura del file e deduce automaticamente il tipo e le colonne
"""

import re
from typing import Dict, List, Tuple, Optional

def analyze_csv_structure(content_bytes: bytes) -> Dict:
    """
    Analizza la struttura di un file CSV e deduce automaticamente:
    - Tipo di file (channels/traffic/unknown)
    - Colonne disponibili
    - Pattern di riconoscimento
    """
    try:
        text = content_bytes.decode("utf-8", errors="ignore")
        lines = text.splitlines()
    except Exception:
        return {"type": "unknown", "columns": [], "confidence": 0, "reason": "Cannot decode file"}
    
    # Cerca la sezione "Freeform table"
    freeform_start = None
    for i, line in enumerate(lines):
        if "Freeform table" in line:
            freeform_start = i
            break
    
    if freeform_start is None:
        return {"type": "unknown", "columns": [], "confidence": 0, "reason": "No Freeform table found"}
    
    # Analizza le righe dopo "Freeform table"
    header_lines = []
    data_lines = []
    
    for i in range(freeform_start + 1, min(freeform_start + 10, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        if line.startswith(","):
            header_lines.append(line)
        elif not line.startswith("#") and "," in line:
            data_lines.append(line)
            if len(data_lines) >= 3:  # Abbastanza dati per analizzare
                break
    
    if not header_lines:
        return {"type": "unknown", "columns": [], "confidence": 0, "reason": "No header found"}
    
    # Estrai le colonne dalla prima riga header
    first_header = header_lines[0]
    columns = [col.strip() for col in first_header.split(",")[1:]]  # Skip first empty column
    
    # Analizza il tipo di file basandosi sulle colonne e sui dati
    analysis = analyze_file_type(columns, data_lines)
    
    return {
        "type": analysis["type"],
        "columns": columns,
        "confidence": analysis["confidence"],
        "reason": analysis["reason"],
        "numeric_columns": analysis["numeric_columns"],
        "page_column": "Page"  # Adobe Analytics usa sempre "Page" come prima colonna
    }

def analyze_file_type(columns: List[str], data_lines: List[str]) -> Dict:
    """
    Analizza il tipo di file basandosi sulle colonne e sui dati di esempio
    """
    
    # Keywords per identificare i tipi di file
    traffic_keywords = ["entries", "visitors", "views", "exit", "time", "rate"]
    channels_keywords = ["search", "direct", "internal", "referring", "social", "paid"]
    
    # Punteggio per tipo di file
    traffic_score = 0
    channels_score = 0
    
    # Analizza le colonne
    for col in columns:
        col_lower = col.lower()
        
        # Traffic keywords
        for keyword in traffic_keywords:
            if keyword in col_lower:
                traffic_score += 1
                break
        
        # Channels keywords  
        for keyword in channels_keywords:
            if keyword in col_lower:
                channels_score += 1
                break
    
    # Analizza i dati di esempio per confermare
    if data_lines:
        sample_data = data_lines[0].split(",")[1:]  # Skip Page column
        
        # Se i dati sembrano essere conteggi/percentuali (numeri)
        numeric_count = 0
        for value in sample_data:
            try:
                float(value.strip())
                numeric_count += 1
            except:
                pass
        
        # Se la maggior parte dei valori sono numerici, probabilmente è un file di dati
        if numeric_count > len(sample_data) * 0.7:
            # Distingui tra traffic e channels basandosi sui nomi delle colonne
            if traffic_score > channels_score:
                return {
                    "type": "traffic",
                    "confidence": min(0.9, 0.5 + traffic_score * 0.1),
                    "reason": f"Detected traffic columns: {[col for col in columns if any(k in col.lower() for k in traffic_keywords)]}",
                    "numeric_columns": columns
                }
            elif channels_score > 0:
                return {
                    "type": "channels", 
                    "confidence": min(0.9, 0.5 + channels_score * 0.1),
                    "reason": f"Detected channel columns: {[col for col in columns if any(k in col.lower() for k in channels_keywords)]}",
                    "numeric_columns": columns
                }
    
    # Fallback: se non riusciamo a distinguere chiaramente
    if traffic_score > 0 or channels_score > 0:
        if traffic_score >= channels_score:
            return {
                "type": "traffic",
                "confidence": 0.6,
                "reason": f"Uncertain, but appears to be traffic (score: {traffic_score})",
                "numeric_columns": columns
            }
        else:
            return {
                "type": "channels",
                "confidence": 0.6, 
                "reason": f"Uncertain, but appears to be channels (score: {channels_score})",
                "numeric_columns": columns
            }
    
    return {
        "type": "unknown",
        "confidence": 0,
        "reason": "Cannot determine file type from columns",
        "numeric_columns": []
    }

def is_likely_adobe_analytics_csv(content_bytes: bytes) -> bool:
    """
    Verifica se il file è probabilmente un export di Adobe Analytics
    """
    try:
        text = content_bytes.decode("utf-8", errors="ignore")
        lines = text.splitlines()[:20]
        text_sample = "\n".join(lines)
        
        # Cerca indicatori tipici di Adobe Analytics
        indicators = [
            "Freeform table",
            "Report suite:",
            "# Date:",
            "# Panel",
            "Page,"
        ]
        
        found_indicators = sum(1 for indicator in indicators if indicator in text_sample)
        return found_indicators >= 2  # Almeno 2 indicatori devono essere presenti
        
    except Exception:
        return False

def get_flexible_columns(content_bytes: bytes) -> List[str]:
    """
    Ottieni le colonne effettive del file, indipendentemente dai nomi specifici
    """
    analysis = analyze_csv_structure(content_bytes)
    return analysis.get("columns", [])

def is_channels_csv_flexible(content_bytes: bytes) -> bool:
    """
    Versione elastica del rilevamento file channels
    """
    if not is_likely_adobe_analytics_csv(content_bytes):
        return False
    
    analysis = analyze_csv_structure(content_bytes)
    return analysis["type"] == "channels" and analysis["confidence"] > 0.5

def is_traffic_csv_flexible(content_bytes: bytes) -> bool:
    """
    Versione elastica del rilevamento file traffic
    """
    if not is_likely_adobe_analytics_csv(content_bytes):
        return False
    
    analysis = analyze_csv_structure(content_bytes)
    return analysis["type"] == "traffic" and analysis["confidence"] > 0.5

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python flexible_parser.py <file_csv>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    with open(file_path, 'rb') as f:
        content = f.read()
    
    analysis = analyze_csv_structure(content)
    print(f"=== ANALISI ELASTICA ===")
    print(f"Tipo: {analysis['type']}")
    print(f"Confidenza: {analysis['confidence']:.1%}")
    print(f"Colonne: {analysis['columns']}")
    print(f"Ragione: {analysis['reason']}")
    print(f"È Adobe Analytics: {is_likely_adobe_analytics_csv(content)}")
