# QR Box Inventory

Local-first QR labeling for garage boxes. Add a box, print a QR, scan it with a phone to see what’s inside. Runs on your laptop or a Raspberry Pi. Uses a single `boxes.json` file—no database.

## Features

* **Add / edit / delete boxes**
* **Add / edit / delete items** inside each box
* **Public read-only view** for each box at `/b/<box_id>` (what the QR opens)
* **Printable QR sheet** at `/labels` (2×1″ label layout; also fine on plain paper)
* **JSON import/export** for backup or migration
* **Optional edit PIN** (`ADMIN_PIN`) for light protection on a home network

---

## Routes

* `/` – Home (list boxes, add a box, import/export, QR shortcuts)
* `/b/<box_id>` – Public read-only box page (linked by QR)
* `/boxes/<box_id>` – Edit box (name/location, items)
* `/labels` – All QR labels on one page (print this)
* `/qr/<box_id>.png` – PNG of a single label (2×1″) or a square QR (`?style=qr`)

---

## Quickstart (local)

### 1) Requirements

* Python 3.10+
* macOS/Linux/Windows

### 2) Create and activate a venv

```bash
python3 -m venv venv
source venv/bin/activate
# Windows (PowerShell): .\venv\Scripts\Activate.ps1
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Configure `.env`

For local development, use `localhost` so links work on your machine:

```
BASE_URL=http://localhost:8000
PORT=8000
ADMIN_PIN=
```

> Note: `BASE_URL` is what gets encoded into the QR codes.
> `localhost` is **not** reachable from your phone. To test phone scanning, change `BASE_URL` to your laptop’s LAN hostname/IP (e.g., `http://Your-Mac.local:8000`), restart, then re-open `/labels`.

### 5) Run the app

```bash
python garage_boxes.py
# or with auto-reload:
uvicorn garage_boxes:app --host 0.0.0.0 --port 8000 --reload
```

### 6) Use it

* Open **[http://localhost:8000](http://localhost:8000)**
* Add a box (and optionally items during creation if you enabled the “items” textarea in the form)
* Click **Edit** to add/edit/delete items
* Visit **/labels** and print the page for stickers or paper
* **/export** downloads your current `boxes.json`

---

## Data model (`boxes.json`)

```json
{
  "boxes": [
    {
      "id": "hex-uuid",
      "name": "Camping Gear",
      "location": "Garage – Rack B, Bin 3",
      "items": [
        {"name": "Tent (2-person)", "qty": 1},
        {"name": "Sleeping bag", "qty": 2}
      ]
    }
  ]
}
```

* **location** is a human hint (“Garage – Shelf A2”, “Closet – Top shelf”); it’s optional.

---

## Editing & deleting

* **Edit a box** (name/location): `/boxes/<box_id>` → Save Box
* **Delete a box**: `/boxes/<box_id>` → type `DELETE` to confirm
* **Edit an item**: inline on `/boxes/<box_id>`
* **Delete an item**: inline on `/boxes/<box_id>`

> PIN: If `ADMIN_PIN` is set in `.env`, add/update/delete actions require the PIN. Leave it blank for frictionless edits on your LAN.

---

## Printing labels

* Go to **/labels** and print from your browser.
* The label image is 384×192 px (2×1″ at 192 DPI), widely compatible with thermal labelers; it also prints fine on plain paper to cut out.

---

## Testing from a phone

* Your phone must be on the **same Wi-Fi**.
* Set `BASE_URL` to a LAN-reachable host (e.g., `http://Your-Mac.local:8000` or `http://192.168.x.y:8000`).
* Restart the app, open **/labels**, and scan with the phone camera.
* If `.local` doesn’t resolve on Android, use the IP.

---

## Deploy on Raspberry Pi

1. **Prep the Pi**

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv avahi-daemon
sudo systemctl enable --now avahi-daemon   # enables raspberrypi.local
```

2. **Clone & install**

```bash
cd ~
git clone https://github.com/dhruv1220/qr-box-inventory.git
cd qr-box-inventory
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. **Pi `.env`**

```
BASE_URL=http://raspberrypi.local:8000
PORT=8000
ADMIN_PIN=1234          # optional
```

4. **Run**

```bash
python garage_boxes.py
# test from a phone: http://raspberrypi.local:8000
```

5. **Run on boot (systemd)**

```bash
sudo tee /etc/systemd/system/qr-box-inventory.service >/dev/null <<'EOF'
[Unit]
Description=QR Box Inventory
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/qr-box-inventory
ExecStart=/home/pi/qr-box-inventory/venv/bin/python garage_boxes.py
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now qr-box-inventory
```

**Family access:** Everyone on the home Wi-Fi can use `http://raspberrypi.local:8000`. If `.local` doesn’t work, use the Pi’s IP (consider setting a DHCP reservation).

---

## Troubleshooting

* **QR opens nothing on phone** → `BASE_URL` is `localhost`. Change it to the Pi/laptop host or IP, restart, re-print `/labels`.
* **Phone can’t reach the app** → not on the same network, guest/isolated Wi-Fi, or OS firewall blocked Python.
* **Edits prompt for PIN a lot** → set `ADMIN_PIN=` (empty) for frictionless development.

---

## Repo hygiene

* Add a template and ignore secrets:

  * `.env.example`

    ```
    BASE_URL=http://raspberrypi.local:8000
    PORT=8000
    ADMIN_PIN=
    ```
  * `.gitignore` add: `.env`

