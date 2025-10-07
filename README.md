# CSV Cleaner - Adobe Analytics Data Processor

Un'applicazione Flask per processare file CSV RAW da Adobe Analytics, con supporto per dati di canali e traffico.

## 🚀 Funzionalità

- **Upload Drag & Drop**: Caricamento intuitivo di file CSV
- **Riconoscimento Automatico**: Identifica automaticamente file channels o traffic
- **Parsing Elastico**: Si adatta automaticamente ai nomi delle colonne
- **Elaborazione Intelligente**: Normalizza URL, estrae titoli, divide per lingua
- **Export Excel**: Genera file XLSX con grafici e analisi
- **CSP Sicuro**: Headers di sicurezza configurati per produzione

## 📁 Struttura

```
├── app.py                 # Applicazione Flask principale
├── csv_pipeline.py       # Logica di parsing CSV
├── flexible_parser.py    # Parser elastico per riconoscimento file
├── debug_file.py         # Script di debug per analisi file
├── static/
│   └── js/
│       └── upload.js     # JavaScript per drag & drop
├── templates/            # Template HTML
└── requirements.txt      # Dipendenze Python
```

## 🛠️ Installazione Locale

```bash
# Clona il repository
git clone <repository-url>
cd csv-cleaner

# Installa dipendenze
pip install -r requirements.txt

# Avvia l'applicazione
python3 app.py
```

L'applicazione sarà disponibile su `http://localhost:8080`

## 🌐 Deploy su Render

Il progetto è configurato per il deploy automatico su Render.com:

- **File di configurazione**: `render.yaml`
- **Build command**: `pip install -r requirements.txt`
- **Start command**: `python3 app.py`
- **Variabili ambiente**: Configurate in `render.yaml`

## 📊 Tipi di File Supportati

### File Channels
- Riconosce automaticamente colonne come:
  - Organic Search, Direct, Internal traffic
  - Referring Domains, Social Networks, Paid Search
- Si adatta a variazioni nei nomi delle colonne

### File Traffic  
- Riconosce colonne come:
  - Entries, Exit Rate, Unique Visitors
  - Page Views, Time Spent per Visit

## 🔧 Debug

Usa `debug_file.py` per analizzare file problematici:

```bash
python3 debug_file.py path/to/file.csv
```

## 🔒 Sicurezza

- **CSP Headers**: Configurati per bloccare script inline
- **File Statici**: JavaScript servito da file esterni
- **Validazione Input**: Controlli sui file caricati

## 📝 Changelog

### v2.0 - Parser Elastico
- ✅ Riconoscimento automatico dei tipi di file
- ✅ Adattamento ai nomi delle colonne effettive
- ✅ Risoluzione problemi CSP
- ✅ Sistema di debug migliorato

### v1.0 - Versione Base
- Upload e processing file CSV Adobe Analytics
- Export Excel con grafici