# BoltFaucet ⚡🚰

__Your Lightning ticket to free Satoshis — authenticated and secure via Telegram and LNbits.__

[![License](https://img.shields.io/github/license/AxelHamburch/BoltFaucet)](LICENSE)
![Lightning Network](https://img.shields.io/badge/Lightning-Network-F7931A?logo=bitcoin)
![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-2CA5E0?logo=telegram)
![Powered by LNbits](https://img.shields.io/badge/Powered%20by-LNbits-E829D3)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

BoltFaucet is a Telegram bot that enables easy, secure Satoshis giveaways through the Bitcoin Lightning Network.
Thanks to Telegram user authentication and LNbits voucher integration, BoltFaucet ensures every withdrawal is legitimate and abuse-proof.

### Features

- ⚡ Lightning-Fast Satoshi Withdrawals — powered by LNURL-withdraw and LNbits.
- 🔒 User Authentication — prevents faucet abuse by linking Telegram user IDs.
- 📲 One-Click Claiming — users simply tap a button to receive a unique QR code.
- 🛡️ Voucher System — backed by LNbits Wallet Accounts for secure voucher generation.
- 🧩 Simple Integration — easily deployable with minimal setup.

### How It Works

1. The user presses a button in Telegram.
2. The bot sends a unique LNURL-withdraw QR code.
3. The user claims their Sats with their Lightning wallet.
4. Telegram ID is stored to prevent multiple claims.

### Why BoltFaucet?

> Prevent faucet abuse. Gift Satoshis with confidence.

Built for projects, communities, and Lightning fans who want to share sats — without worrying about spam or exploitation.

---

### Was brauche ich und wie richte ich BoltFaucet ein?

Du brauchst ein LNbits Wallet, ein Telegram Bot und dieses Repository. Thats it!

1. Leg dir ein LNbits Wallet an und beschaff dir den Admin key für das Wallet.
2. Erstellte mit dem [t.me/BotFather](https://t.me/BotFather) einen neuen Bot und lass dir von ihm den Access Token dafür geben.
3. Nutze den [t.me/userinfobot](https://t.me/userinfobot) um deine eigene ID herauszubekommen.
4. Installiere Vorbedingungen und das Projekt auf einem Server:
    ```bash
    sudo apt install python3.11-venv python3.11-distutils
    git clone https://github.com/AxelHamburch/BoltFaucet.git
    ```
5. Erstelle eine .env Datei und öffne sie zum Bearbeiten:
    ```bash
    cd BoltFaucet
    cp example.env .env
    nano .env
    ```
6. Passe mindestens an:
   - LNbits API key
   - LNbits URL
   - Telegram Bot Access Token
   - Deine Telegram Chat/User-ID
   
7. Installiere die Abhängigkeiten:
    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install Wheel
    python3.11 -m pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    ```
8. Starte die Anwendung.
    ```bash
     python3.11 app.py
    ```
9.  Speicher dir die Seite HomepageButton.html irgendwo ab und tausch in der ersten Zeile `YourBotName_bot` gegen den Namen deines eigenen Bots.
10. Jetzt Doppelklick die html-Datei um sie zu öffnen und den Button anzuzeigen. 
11. Klick auf den Button und lass dich zu deinem Bot weiterleiten um ihn zu testen.
12. Jetzt sollte euch der Bot den Voucher anzeigen. 🎉 






