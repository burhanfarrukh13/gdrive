# Remote Access — letting the team browse in from anywhere

Drive Manager runs on ONE machine (the "host" — e.g. the office PC).
Nobody else installs anything. They just open a browser to a URL and log
in with the account you create for them on the Team page.

How far that URL reaches depends on where people are:

- **Same office / same WiFi** → the host's local network address is enough.
- **Different cities / remote workers** → the host needs to be reachable
  over the internet. Recommended way: a tunnel (Cloudflare Tunnel or
  ngrok). Do NOT port-forward your home/office router directly to this
  app — a tunnel gives you HTTPS and doesn't expose your router.

The app already listens on `0.0.0.0:8000`, so it accepts connections
from other machines, not just itself — nothing to change there.

---
## Option A — Same building / same WiFi only

1. On the host PC, find its local IP:
   `ipconfig` → look for "IPv4 Address" (e.g. `192.168.1.42`).
2. Allow the port through Windows Firewall (run once, as Administrator):
   ```
   netsh advfirewall firewall add rule name="Drive Manager" dir=in action=allow protocol=TCP localport=8000
   ```
3. Teammates on the same WiFi open: `http://192.168.1.42:8000`

This local IP can change if the router reassigns it — for anything
beyond a same-day test, set a DHCP reservation for the host PC in your
router settings so the IP stays fixed.

---
## Option B — Team members in different locations (recommended)

Use a tunnel. It gives you one stable **HTTPS** address that always
points at the host PC, wherever it is, without opening router ports.

### Cloudflare Tunnel (free, no bandwidth limits, needs a domain you control)

1. Download `cloudflared` for Windows:
   https://github.com/cloudflare/cloudflared/releases (get `cloudflared-windows-amd64.exe`)
2. `cloudflared tunnel login` → authorize against your Cloudflare account
   (add your domain to Cloudflare first, free plan is fine).
3. `cloudflared tunnel create drivemanager`
4. `cloudflared tunnel route dns drivemanager drive.yourdomain.com`
5. Run it: `cloudflared tunnel run --url http://localhost:8000 drivemanager`
6. Team opens: `https://drive.yourdomain.com`

### ngrok (free, no domain needed — fastest to set up)

1. Create a free account at https://ngrok.com, install the Windows agent.
2. Claim one free **static domain** (Dashboard → Domains) — this is what
   keeps the URL from changing every restart.
3. Run: `ngrok http --domain=your-chosen-name.ngrok-free.app 8000`
4. Team opens: `https://your-chosen-name.ngrok-free.app`

Either way, once you have the permanent URL, update
`gdrive-platform/.env`:
```
APP_BASE_URL=https://drive.yourdomain.com
```
(cosmetic/used in links the app generates — not required for login to work.)

---
## Keep it running

- The tunnel command (Option B) and `start.bat` / `DriveManager.exe` both
  need to keep running on the host PC. Don't close their windows.
- Turn off sleep on the host PC: Settings → System → Power → set
  "Sleep" to Never (at least while plugged in).
- To auto-start on boot (so a reboot doesn't take the app down):
  Task Scheduler → Create Task → Trigger: "At log on" → Action: run
  `DriveManager.exe` (and, separately, your tunnel command) → check
  "Run whether user is logged on or not" if you want it headless.

---
## Team logins

Each teammate should get their own account (Team page → Add member),
with a role matching what they need (see `ROLES.md`). Don't hand out
the owner/admin login from `ADMIN_CREDENTIALS.txt` — that's for the
person administering the system, not day-to-day use.
