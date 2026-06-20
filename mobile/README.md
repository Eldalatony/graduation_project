# SHEMMS Mobile

Read-only mobile viewer for SHEMMS appliance live readings. Built with Expo + React Native.

## First-time setup

```bash
cd mobile
npm install
```

Copy `.env.example` to `.env` and set `EXPO_PUBLIC_API_URL` to your PC's LAN IP, e.g.:

```
EXPO_PUBLIC_API_URL=http://192.168.1.20:3001
```

Find your IP on Windows with `ipconfig` (look for IPv4 under your Wi-Fi adapter).

## Run

```bash
npm start
```

A QR code appears in the terminal. Install **Expo Go** on your phone (Play Store / App Store) and scan it. Your phone and PC must be on the same Wi-Fi network, and the SHEMMS backend must be running on port 3001.

If Windows Firewall blocks the connection, allow Node.js through on the first prompt.

## Login

Use the same email/password you registered with on the web app.
