# CSV Processor

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
- `Canali_.xlsx` - Dati di canalizzazione con grafici
- `Traffico_.xlsx` - Dati di traffico con grafici  
- `Completo_.xlsx` - File unico con tutti i dati

### Grafici inclusi:
- **Canali**: Grafico a torta (distribuzione) + Grafico a barre (confronto per articolo)
- **Traffico**: Grafico a barre (confronto per articolo)


**Sviluppato per uso personale** - Automazione del processing dei dati Insights/Analytics
