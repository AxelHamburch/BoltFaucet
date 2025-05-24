# BoltFaucet ⚡🚰

__Your Lightning ticket to free Satoshis — authenticated and secure via Telegram and LNbits.__

[![License](https://img.shields.io/github/license/AxelHamburch/BoltFaucet)](LICENSE)
![Lightning Network](https://img.shields.io/badge/Lightning-Network-F7931A?logo=bitcoin)
![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-2CA5E0?logo=telegram)
![Powered by LNbits](https://img.shields.io/badge/Powered%20by-LNbits-E829D3)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)


BoltFaucet is a Telegram bot that enables easy, secure Satoshis giveaways through the Bitcoin Lightning Network.
Thanks to Telegram user authentication and LNbits voucher integration, BoltFaucet ensures every withdrawal is legitimate and abuse-proof.

> Based on original work by [DoktorShift](https://github.com/DoktorShift).


### Features

- ⚡ Lightning-Fast Satoshi Withdrawals — powered by LNURL-withdraw and LNbits.
- 🔒 User Authentication — prevents faucet abuse by linking Telegram user IDs.
- 📲 One-Click Claiming — users simply tap a button to receive a unique QR code.
- 🛡️ Voucher System — backed by LNbits Wallet Accounts for secure voucher generation.
- 🍀 Lucky Bonus System — configurable chance for users to win bonus sats.
- 📊 Statistics Tracking — monitor usage, lucky wins, and voucher supply.
- 🧩 Simple Integration — easily deployable with minimal setup.

### How It Works

1. The user presses a button in Telegram.
2. The bot sends a unique LNURL-withdraw QR code.
3. The user claims their Sats with their Lightning wallet.
4. Telegram ID is stored to prevent multiple claims.
5. Lucky users may receive an additional bonus voucher automatically.

### Why BoltFaucet?

> Prevent faucet abuse. Gift Satoshis with confidence.

Built for projects, communities, and Lightning fans who want to share sats — without worrying about spam or exploitation.


## What do I need and how do I set up BoltFaucet?

You’ll need an LNbits wallet, a Telegram bot, and this repository. That’s it!

1. Create an LNbits wallet and get the admin key for your wallet.
2. Create a new bot using [t.me/BotFather](https://t.me/BotFather) and obtain the access token.
3. Use [t.me/userinfobot](https://t.me/userinfobot) to find out your own Telegram user ID.
4. Install the required dependencies and clone the project on your server:
    ```bash
    sudo apt install python3.11-venv python3.11-distutils
    git clone https://github.com/AxelHamburch/BoltFaucet.git
    ```
5. Create a `.env` file and open it for editing:
    ```bash
    cd BoltFaucet
    cp example.env .env
    nano .env
    ```
6. At minimum, update the following settings in the `.env` file:
   - LNbits API key
   - LNbits URL
   - Telegram Bot Access Token
   - Deine Telegram Chat/User-ID
   
7. Install the Python dependencies:
    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install Wheel
    python3.11 -m pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    ```
8. Start the application:
    ```bash
     python3.11 app.py
    ```
9.  Save the `HomepageButton.html` file locally and replace `YourBotName_bot` in the first line of the public link with the name of your own bot.
10. Double-click the HTML file to open it and display the button.
11. Click the button to be redirected to your bot for testing.
12. The bot should now display a voucher for you. 🎉

As an admin, you can generate as many vouchers as you like. All other users are limited to one voucher. Each user's Telegram ID is stored in the database. If a user tries to claim a second time, they will receive a notification.

> Hey @user, you've already claimed 21 sats 🎉 Let's keep it fair - thank you! 🙏



### Bot Commands

- `/getvoucher` - Claim your sats
- `/info` - Learn about the lucky bonus feature
- `/lucky` - View lucky statistics and recent winners
- `/stats` - Admin only: Display voucher supply and usage statistics
- `/cleanup` - Admin only: Remove invalid database entries


### Lucky Bonus Feature

The lucky bonus system adds excitement to your faucet by giving users a small chance to win additional sats:

- **Configurable odds**: Set the percentage chance for lucky wins
- **Bonus amount**: Define how many extra sats lucky winners receive
- **Automatic tracking**: All lucky wins are recorded with statistics
- **Recent winners**: Display recent lucky winners to build excitement
- **Fair distribution**: Lucky vouchers are managed separately from regular vouchers

---

## BoltFaucet Autostart Service

After a successful test, stop the application with `CTRL+C`.
Deactivate the virtual environment by running `deactivate`, and then add this service.

1. Create new system service:
```bash
sudo nano /etc/systemd/system/boltfaucet.service
```

2. Fill in the file with the following information and customize `youruser` in __five__ places:

```plaintext
[Unit]
Description=BoltFaucet
After=network.target

[Service]
User=youruser
WorkingDirectory=/home/youruser/BoltFaucet
ExecStart=/home/youruser/BoltFaucet/venv/bin/python /home/youruser/BoltFaucet/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

3. Activate, start and monitor:
```bash
sudo systemctl enable boltfaucet
sudo systemctl start boltfaucet
sudo systemctl status boltfaucet
```

From now on, boltfaucet will start automatically with every restart. 🎉

However, if you have problems, you can call up the logs with the following command:

```bash
sudo journalctl -u boltfaucet -f --since "2 hour ago"
```

## Acknowledgements

This project is based on the original work by [DoktorShift](https://github.com/DoktorShift).  
Many thanks for sharing the code and inspiring this implementation!

A heartfelt thank you to the entire [LNbits Team](https://github.com/lnbits) for your incredible work on the outstanding [LNbits](https://lnbits.com/) project. Your contributions make solutions like this possible!

## Like this project?

<div align="center">

LN - Address

  <img src="./assets/ln-axelhamburch-xyz.jpg" width="100">

[axelhamburch@ereignishorizont.xyz](lightning:axelhamburch@ereignishorizont.xyz)
</div>






