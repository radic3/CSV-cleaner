# INBIZ CSV Processor

Un'applicazione web Flask per processare automaticamente i file CSV RAW di Adobe Analytics, separando i contenuti IT/EN e normalizzando i titoli degli articoli.

## 🚀 Funzionalità

- **Upload multiplo**: Carica più file CSV contemporaneamente
- **Separazione IT/EN**: Riconosce automaticamente i contenuti italiani e inglesi
- **Normalizzazione titoli**: Estrae e pulisce i titoli degli articoli dagli URL
- **Grafici nativi Excel**: Genera grafici dinamici e modificabili nei file XLSX
- **Download multipli**: File separati per Canali, Traffico e un file completo

## 📊 Tipi di file supportati

- **Canali RAW**: File di canalizzazione da Adobe Analytics
- **Traffico RAW**: File di traffico da Adobe Analytics

## 🎯 Output

### File generati:
- `INBIZ_Canali_.xlsx` - Dati di canalizzazione con grafici
- `INBIZ_Traffico_.xlsx` - Dati di traffico con grafici  
- `INBIZ_Completo_.xlsx` - File unico con tutti i dati

### Grafici inclusi:
- **Canali**: Grafico a torta (distribuzione) + Grafico a barre (confronto per articolo)
- **Traffico**: Grafico a barre (confronto per articolo)

## 🚀 Deployment su Render.com

### **Deploy automatico:**
1. **Fai fork** di questa repository
2. **Vai su [Render.com](https://render.com)** e crea un account
3. **Clicca "New +"** → **"Web Service"**
4. **Collega GitHub** e seleziona la repository
5. **Configurazione**:
   - **Name**: `inbiz-csv-processor`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
6. **Clicca "Create Web Service"**

L'applicazione sarà disponibile su `https://inbiz-csv-processor.onrender.com`

## 🛠️ Installazione locale

1. **Clona la repository**:
```bash
git clone https://github.com/[username]/inbiz-csv-processor.git
cd inbiz-csv-processor
```

2. **Crea ambiente virtuale**:
```bash
python3 -m venv .venv
source .venv/bin/activate  # Su Windows: .venv\Scripts\activate
```

3. **Installa dipendenze**:
```bash
pip install -r requirements.txt
```

4. **Avvia l'applicazione**:
```bash
python app.py
```

L'applicazione sarà disponibile su `http://localhost:8090`

## 📁 Struttura del progetto

```
inbiz-csv-processor/
├── app.py                 # Applicazione Flask principale
├── inbiz_pipeline.py      # Logica di parsing dei CSV
├── url_title.py          # Estrazione e normalizzazione titoli
├── requirements.txt      # Dipendenze Python
├── render.yaml           # Configurazione Render.com
├── Procfile              # Comando di avvio
├── templates/            # Template HTML
│   ├── upload.html       # Pagina di upload
│   ├── confirm.html      # Pagina di conferma
│   └── results.html      # Pagina risultati
├── .gitignore           # File da ignorare
├── LICENSE              # Licenza MIT
└── README.md            # Questo file
```

## 🔧 Configurazione

### Porta personalizzata
```bash
PORT=8080 python app.py
```

### Variabili d'ambiente
- `PORT`: Porta del server (default: 8090)

## 📝 Utilizzo

1. **Carica i file**: Trascina i CSV RAW di Adobe Analytics nella pagina web
2. **Conferma**: Verifica che i file siano stati caricati correttamente
3. **Elabora**: Clicca "Vai all'elaborazione" per processare i dati
4. **Scarica**: Ottieni i file XLSX con i dati processati e i grafici

## 🎨 Caratteristiche tecniche

- **Framework**: Flask (Python)
- **Elaborazione dati**: Pandas
- **Grafici Excel**: Openpyxl
- **Interfaccia**: HTML/CSS/JavaScript vanilla
- **Upload**: Drag & drop multiplo

## 📈 Esempio di output

I file XLSX contengono:
- **Tabelle complete** con riga somma
- **Grafici nativi Excel** completamente modificabili
- **Fogli separati** per IT e EN
- **Dati normalizzati** con titoli puliti

## 🤝 Contributi

I contributi sono benvenuti! Per favore:

1. Fai un fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Commit le tue modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📄 Licenza

Questo progetto è distribuito sotto licenza MIT. Vedi il file `LICENSE` per maggiori dettagli.

## 🆘 Supporto

Per problemi o domande, apri una issue su GitHub.

---

**Sviluppato per INBIZ** - Automazione del processing dei dati Adobe Analytics
