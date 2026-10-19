# Google Cloud Setup — Service Account for Drive Manager

This is the only setup the client (or you) has to do. Take it once, ~10 minutes.

> **You will not share the client's password with this app, ever.** Google Drive service accounts are a *separate* identity — a "robot user" that the app uses to call the Drive API.

---

## 1. Create a Google Cloud project

1. Open https://console.cloud.google.com/
2. Top-left, click the project dropdown → **New Project**
3. Name: `Drive Manager` (or anything you like)
4. Click **Create**

## 2. Enable the Google Drive API

1. In the left menu (☰) → **APIs & Services** → **Library**
2. Search `Google Drive API`
3. Click it → click **Enable**

(You do **not** need to enable any OAuth consent screen — Service Accounts skip that entirely.)

## 3. Create a Service Account

1. Left menu → **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account** at the top
3. **Service account name:** `drive-manager-bot` (or whatever)
4. **Service account ID:** auto-filled, fine
5. Skip "Grant access" and "Grant users access" — we don't need IAM roles for Drive; sharing is done in Drive itself.
6. Click **Done**

## 4. Create & download the JSON key

1. Click the service account you just created
2. Top tab → **Keys** → **Add Key** → **Create new key**
3. Choose **JSON** → **Create**
4. A `.json` file downloads. **This is the file the app needs.**
5. Rename it to `service_account.json`
6. Move it into your project:
   ```
   D:\claude\gdrive\gdrive-platform\secrets\service_account.json
   ```

> ⚠️ Treat this file like a password. Don't commit it to git. Don't share it. Don't email it.

## 5. Find the Service Account email

Open the JSON file in a text editor. You'll see:

```json
{
  "type": "service_account",
  "project_id": "drive-manager-xxxxx",
  "client_email": "drive-manager-bot@drive-manager-xxxxx.iam.gserviceaccount.com",
  ...
}
```

The value of **`client_email`** is what you'll share Drive folders with. Looks like:

```
drive-manager-bot@drive-manager-xxxxx.iam.gserviceaccount.com
```

## 6. Share Drive folders with the Service Account

This is the only step the **client** does, in their own Google Drive.

### In the **main Drive account** (the one your client uses to manage all 5 source Drives):

1. Open https://drive.google.com
2. **Click "My Drive" at the top of the left sidebar** (so you're sharing the root, not a single folder)
3. Right-click → **Share** → **Manage access** (or click the share icon)
4. Paste the service account email (`drive-manager-bot@…iam.gserviceaccount.com`)
5. Set role to **Editor** (not Viewer — the app needs to create/revoke permissions)
6. **Uncheck** "Notify people" (it's a robot, it won't read the email)
7. Click **Share**

That's it — **one share at the root of the main Drive.** All folders underneath (including the 5 source Drives that are shared into main Drive) are now visible to the service account with Editor rights.

### Why root-level sharing works

- The service account inherits access to all folders **owned by** main Drive, plus all folders **explicitly shared with** main Drive.
- It can call `permissions.create` / `permissions.delete` on any of those folders.
- It does **not** need access to the underlying source Drives directly — it only needs main Drive's view of them.

### Edge case — Viewer-only shares from source drives

If any of your 5 source Drives shared a folder with main Drive as **Viewer** (read-only), the service account can see the folder but cannot manage permissions on it. To fix:

- In the **source Drive**, change the share for main Drive to **Editor**.

You'll only need to do this if you see errors like "Permission denied" when trying to grant access to a specific folder.

## 7. Verify everything works

With the JSON in place and the share done, restart the app:

```bash
python run.py
```

Open http://localhost:8000, log in, go to **Drive Folders** → paste any folder ID or URL → click **Verify & add**.

- ✅ If it adds, you're done.
- ❌ If it errors with `Folder not found or service account has no access…`, double-check that the folder is **inside** main Drive's tree (either owned or shared in) and that the share is at **Editor**.

## 8. Optional — restrict to a Google Workspace domain

If the client's accounts are all under one Google Workspace (e.g. `@hisdomain.com`), you can restrict the service account to only act on that domain. In `.env`:

```
GOOGLE_WORKSPACE_DOMAIN=hisdomain.com
```

This requires the project to be inside that Workspace, and the SA needs domain-wide delegation. Skip for the simple case.

---

## Quick checklist

- [ ] Google Cloud project created
- [ ] Drive API enabled
- [ ] Service Account created
- [ ] JSON key downloaded → renamed `service_account.json` → placed in `secrets/`
- [ ] SA email added to **main Drive root** as **Editor**
- [ ] App restarted → folder verified

If all 6 are checked, the platform is fully wired up. Students will start receiving time-bound Drive viewer permissions the moment you click **Grant access**.