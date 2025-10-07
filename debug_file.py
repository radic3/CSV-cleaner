#!/usr/bin/env python3
"""
Script per debuggare file CSV problematici
Analizza i file e identifica perché non vengono riconosciuti come channels o traffic
"""

import os
import sys
from pathlib import Path

def analyze_csv_file(file_path):
    """Analizza un file CSV e identifica il problema"""
    print(f"\n=== ANALISI FILE: {file_path} ===")
    
    if not os.path.exists(file_path):
        print(f"❌ ERRORE: File non trovato: {file_path}")
        return
    
    try:
        # Leggi il file come bytes per simulare l'upload
        with open(file_path, 'rb') as f:
            content_bytes = f.read()
        
        # Prova a decodificare
        try:
            text = content_bytes.decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"❌ ERRORE: Impossibile decodificare il file: {e}")
            return
        
        # Analizza le prime 80 righe
        lines = text.splitlines()[:80]
        print(f"📊 File contiene {len(text.splitlines())} righe totali")
        print(f"📝 Analizzando le prime {min(80, len(lines))} righe...")
        
        # Cerca token specifici
        head_lines = [ln.strip() for ln in lines]
        head = "\n".join(head_lines)
        
        print("\n🔍 RICERCA TOKEN:")
        
        # Token per channels
        channels_tokens = [
            "Freeform table",
            "Organic Search", 
            "Direct",
            "Internal traffic",
            "Referring Domains",
            "Social Networks"
        ]
        
        print("\n📈 TOKEN CANALI:")
        for token in channels_tokens:
            found = any(token in ln for ln in head_lines) if token == "Freeform table" else (token in head)
            status = "✅" if found else "❌"
            print(f"  {status} {token}")
        
        # Token per traffic
        traffic_tokens = [
            "Freeform table",
            "Entries",
            "Unique Visitors", 
            "Page Views"
        ]
        
        print("\n🚦 TOKEN TRAFFICO:")
        for token in traffic_tokens:
            found = token in head
            status = "✅" if found else "❌"
            print(f"  {status} {token}")
        
        # Mostra le prime righe per debug
        print(f"\n📋 PRIME 10 RIGHE DEL FILE:")
        for i, line in enumerate(lines[:10], 1):
            print(f"  {i:2d}: {repr(line)}")
        
        # Test delle funzioni di rilevamento
        print(f"\n🧪 TEST FUNZIONI DI RILEVAMENTO:")
        
        # Simula _is_channels_freeform_csv con la nuova logica
        def check_token(token):
            if token == "Freeform table":
                return any(token in ln for ln in head_lines)
            elif isinstance(token, tuple):
                # For tuples like ("Social Networks", "Paid Search"), check if any of them is present
                return any(t in head for t in token)
            else:
                return token in head
        
        channels_ok = all(check_token(tok) for tok in [
            "Freeform table",
            "Organic Search",
            "Direct", 
            "Internal traffic",
            "Referring Domains",
            ("Social Networks", "Paid Search")
        ])
        print(f"  Channels: {'✅ RICONOSCIUTO' if channels_ok else '❌ NON RICONOSCIUTO'}")
        
        # Simula _is_traffic_freeform_csv  
        traffic_ok = (
            "Freeform table" in head
            and "Entries" in head
            and "Unique Visitors" in head
            and "Page Views" in head
        )
        print(f"  Traffic: {'✅ RICONOSCIUTO' if traffic_ok else '❌ NON RICONOSCIUTO'}")
        
        if not channels_ok and not traffic_ok:
            print(f"\n⚠️  PROBLEMA IDENTIFICATO:")
            print(f"   Il file non contiene tutti i token necessari per essere riconosciuto come:")
            
            # Check which channels tokens are missing
            missing_channels = []
            for token in ["Freeform table", "Organic Search", "Direct", "Internal traffic", "Referring Domains", ("Social Networks", "Paid Search")]:
                if not check_token(token):
                    missing_channels.append(token)
            print(f"   - File Channels (mancano: {missing_channels})")
            
            # Check which traffic tokens are missing
            missing_traffic = [t for t in traffic_tokens if t not in head]
            print(f"   - File Traffic (mancano: {missing_traffic})")
            
            print(f"\n💡 SUGGERIMENTI:")
            print(f"   1. Verifica che il file sia un CSV export da Adobe Analytics")
            print(f"   2. Controlla che contenga una tabella 'Freeform table'")
            print(f"   3. Per channels: deve contenere colonne Organic Search, Direct, etc.")
            print(f"   4. Per traffic: deve contenere colonne Entries, Unique Visitors, Page Views")
        
    except Exception as e:
        print(f"❌ ERRORE durante l'analisi: {e}")
        import traceback
        traceback.print_exc()

def main():
    if len(sys.argv) != 2:
        print("Uso: python debug_file.py <percorso_file_csv>")
        print("Esempio: python debug_file.py '../file sus/mio_file.csv'")
        sys.exit(1)
    
    file_path = sys.argv[1]
    analyze_csv_file(file_path)

if __name__ == "__main__":
    main()
