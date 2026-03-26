# Discord-Server-Cloner
# Discord Server Cloner Selfbot

> ⚠️ **Disclaimer:** This tool is for **educational purposes only**. Using selfbots violates Discord's Terms of Service. Use at your own risk. The author is not responsible for any consequences.

A powerful selfbot to clone entire Discord servers – including channels, roles, messages, and attachments – with **high speed** and **smart reuse** of existing channels and webhooks. Supports **proxy rotation**, **adaptive rate‑limit handling**, and **selective channel skipping**.

## ✨ Features

- **Full server clone**: channels (categories, text, voice), roles (permissions, colors, hoist), messages (with all attachments), and webhooks.
- **Smart reuse**: If a target server already has channels with the same names, they will be reused (no duplication). Existing webhooks in those channels are also reused.
- **Skip channels**: Specify source channel IDs to **exclude entirely** from the clone (they won't be created in the target).
- **Purge command**: After cloning, optionally send a custom command (e.g., `&purge all`) in every text channel to clear them.
- **Proxy support**: Use HTTP/HTTPS/SOCKS4/SOCKS5 proxies to rotate IPs and avoid rate limits.
- **Rate‑limit handling**: Exponential backoff for webhook creation, configurable delays for channels and messages.
- **Attachments**: Downloads and uploads images, videos, zips, etc. (up to 8 MB per file, Discord webhook limit).
- **Clean output**: Beautiful console output with emojis and detailed statistics.

## 🚀 How It Works

1. Validates your Discord user token.
2. Fetches the source server (the one to clone).
3. If you choose an existing target server, it lists all its channels.
4. You can optionally **delete all existing channels** in the target, or **reuse them**.
5. You can provide a list of source channel IDs to **skip entirely**.
6. Roles are copied (or reused if names match).
7. Channels are created (or reused) exactly as in the source, preserving categories, permissions, and settings.
8. Existing webhooks in reused channels are detected and reused; new ones are created if needed.
9. Messages are fetched in batches of 100 and sent via webhooks (with full attachment support).
10. (Optional) A purge command is sent to clear channels after cloning.
11. A summary shows how many roles, channels, webhooks, and messages were processed.

## 📦 Requirements

- Python 3.8 or higher
- Dependencies listed in `requirements.txt`

## 🔧 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/discord-server-cloner.git
   cd discord-server-cloner

credit Goes to @ur_daddy619(discord username dm for more stuffs )
# A tool for https://discord.gg/v5cFWxPAy
  
