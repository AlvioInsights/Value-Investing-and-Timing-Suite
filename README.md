# 💎 Value Investing & Timing Suite

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Build Status](https://img.shields.io/github/actions/workflow/status/tuo-username/value-investing-suite/main.yml?branch=main)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=Streamlit&logoColor=white)

Un'applicazione open-source in Python e Streamlit che unisce lo screening fondamentale (ricerca di aziende solide) al timing tecnico (ottimizzazione del punto di ingresso a mercato).
Fornisce metriche chiave (ROIC, FCF, PEG), grafici interattivi, uno scoring algoritmico e genera automaticamente prompt per l'analisi qualitativa tramite AI (ChatGPT/Claude).
Ideato da [Alvioinsights.com](https://alvioinsights.com)e sviluppato da Google Gemini

## 📋 Requisiti di Sistema

- **Sistema Operativo:** Windows, macOS o Linux
- **Python:** Versione 3.9 o superiore installata nel sistema
- **Connessione Internet:** Necessaria per il download dei dati finanziari in tempo reale tramite le API di Yahoo Finance.

## 🚀 Installazione (Aggiornata per superare i blocchi GitHub e macOS)

Per evitare problemi di permessi o conflitti di sistema, ecco la via più sicura per installare la suite.

**1. Scarica il progetto**
Il modo più semplice (se non vuoi usare `git` o hai problemi di password con GitHub) è cliccare sul pulsante verde **"<> Code"** in alto a destra su questa pagina e selezionare **"Download ZIP"**. Estrai la cartella sul tuo computer e aprila con il terminale.

Se preferisci usare Git (assicurati di usare HTTPS):
`git clone https://github.com/alvioinsights/value-investing-suite.git`
`cd value-investing-suite`

**2. Crea l'ambiente virtuale**
Questo passaggio è fondamentale per non "sporcare" il tuo sistema operativo.

*Su Windows:*
`python -m venv venv`
`venv\Scripts\activate`

*Su macOS / Linux:*
*(Nota per utenti Mac: usate sempre `python3` e assicuratevi di aver installato Python via Homebrew se il sistema vi dà errori).*
`python3 -m venv venv`
`source venv/bin/activate`

**3. Installa le dipendenze**
Abbiamo sostituito il vecchio pacchetto `pandas-ta` (non più open-source) con il fork supportato dalla community `pandas-ta-classic`.
`pip install -r requirements.txt`

## ⚡ Avvio Rapido

Una volta attivato l'ambiente virtuale, lancia l'app con:

*Su Windows:*
`streamlit run main.py`

*Su macOS / Linux:*
`python3 -m streamlit run main.py`

Il tuo browser si aprirà automaticamente su `http://localhost:8501`. 

**Esempio reale di utilizzo:**
1. Vai nella Sidebar a sinistra.
2. Alla voce "Modalità" seleziona **Manuale**.
3. Inserisci il ticker **AAPL** (Apple).
4. Clicca su **🚀 Avvia Analisi Completa**.
5. Esplora il tab **Analisi Fondamentale** per vedere i bilanci e usare il prompt AI, poi spostati sul tab **Timing Tecnico** per vedere il punteggio di ingresso (0-100) e il grafico interattivo!

## 📁 Struttura del Progetto

```text
value-investing-suite/
│
├── main.py               # Cuore dell'applicazione (Logica Data Engine e UI Streamlit)
├── requirements.txt      # Elenco delle dipendenze e librerie Python necessarie
├── README.md             # Questo documento di documentazione
└── /dati_test/           # (Opzionale) Cartella dove salvare i tuoi CSV (es. watchlist.csv)
```

## 🤝 Come Contribuire

I contributi sono fondamentali per rendere l'ecosistema open source un posto fantastico per imparare, trarre ispirazione e creare. Qualsiasi contributo tu dia è **molto apprezzato**.

1. Esegui un **Fork** del Progetto (Pulsante in alto a destra su GitHub).
2. Crea il tuo Feature Branch (`git checkout -b feature/MiglioramentoIncredibile`).
3. Fai il Commit dei tuoi cambiamenti (`git commit -m 'Aggiunto un Miglioramento Incredibile'`).
4. Fai il Push sul Branch (`git push origin feature/MiglioramentoIncredibile`).
5. Apri una **Pull Request**.

Assicurati che il codice passi i controlli di qualità e che non alteri il funzionamento core esistente.

## 📄 Licenza

Distribuito sotto la licenza MIT. Vedi il file `LICENSE` per maggiori informazioni. Questo software è fornito a scopo puramente didattico e informativo. Non costituisce sollecitazione al pubblico risparmio o consulenza finanziaria.

---
<div align="center">
  Ideato da <a href="https://alvioinsights.com"><b>Alvioinsights.com</b></a> e sviluppato da <b>Google Gemini AI</b>.
</div>
```
