from __future__ import annotations

import io
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw, ImageFont
import qrcode

# ----------------------------- Config & paths ------------------------------
load_dotenv()  # load .env into os.environ

APP_DIR = Path(__file__).parent.resolve()
DATA_DIR = APP_DIR / "data"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
for p in (DATA_DIR, TEMPLATES_DIR, STATIC_DIR):
    p.mkdir(parents=True, exist_ok=True)

DATA_FILE = DATA_DIR / "boxes_sample.json"

# Settings from environment (strings by default)
BASE_URL = os.getenv("BASE_URL").rstrip("/")
ADMIN_PIN = os.getenv("ADMIN_PIN")  # optional; empty means no PIN required
PORT = int(os.getenv("PORT"))

# ----------------------------- Data layer ----------------------------------
# Structure:
# {
#   "boxes": [
#     {"id": "hex", "name": "Camping Gear", "location": "Garage – Rack B", "items":[{"name":"Tent","qty":1}]}
#   ]
# }
EMPTY = {"boxes": []}

def load_data() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(EMPTY, indent=2), encoding="utf-8")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def save_data(d: Dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

def find_box(d: Dict[str, Any], bid: str) -> Optional[Dict[str, Any]]:
    return next((b for b in d["boxes"] if b["id"] == bid), None)

# ----------------------------- App setup -----------------------------------
app = FastAPI(title="QR Box Inventory")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ----------------------------- Template seeding ----------------------------
def seed(name: str, content: str) -> None:
    path = TEMPLATES_DIR / name
    if not path.exists():
        path.write_text(content.strip(), encoding="utf-8")

seed("layout.html", """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title or "QR Box Inventory" }}</title>
<style>
  :root { --b:#e5e7eb; --t:#111; --m:#555; --btn:#2563eb; }
  body{font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin:16px; line-height:1.5; color:var(--t)}
  .btn{background:var(--btn);color:#fff;border:0;padding:8px 12px;border-radius:10px;cursor:pointer;text-decoration:none;display:inline-block}
  .btn.secondary{background:#f3f4f6;color:#111;border:1px solid var(--b)}
  input[type="text"], input[type="number"]{padding:8px;border:1px solid var(--b);border-radius:10px}
  .card{border:1px solid var(--b);border-radius:14px;padding:12px;margin:10px 0}
  .row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
  .muted{color:var(--m)}
  @media print {.no-print{display:none}}
</style>
</head>
<body>
  <div class="no-print" style="margin-bottom:12px">
    <a href="/" class="btn secondary">Home</a>
    <a href="/labels" class="btn secondary">Print QRs</a>
    <a href="/export" class="btn secondary">Export JSON</a>
  </div>
  {% block content %}{% endblock %}
</body>
</html>
""")

seed("index.html", """
{% extends "layout.html" %}
{% block content %}
<h1>Boxes</h1>
<div class="card no-print">
  <form action="/boxes" method="post" class="row">
    <input name="name" type="text" placeholder="Box name" required>
    <input name="location" type="text" placeholder="Location (optional)">
    <textarea name="items" rows="3" placeholder="One per line: 
Tent,1
Sleeping bag,2
Camp stove x 1"></textarea>
    {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
    <button class="btn">Add Box</button>
  </form>
  <p class="muted" style="margin-top:6px">“Location” is a hint like “Garage – Shelf A2” or “Closet – Top shelf”.</p>
</div>

{% for b in boxes %}
  <div class="card">
    <div class="row">
      <div>
        <div style="font-weight:600">{{ b.name }}</div>
        <div class="muted">Location: {{ b.location or "—" }}</div>
        <div class="muted" style="font-size:12px">ID: {{ b.id }}</div>

        {% if b['items'] and b['items']|length > 0 %}
        <div class="muted" style="margin-top:8px">
            <strong>Items ({{ b['items']|length }}):</strong>
            <ul style="margin:6px 0 0 18px">
            {% for it in b['items'][:5] %}
                <li>{{ it.name }} ×{{ it.qty }}</li>
            {% endfor %}
            {% if b['items']|length > 5 %}
                <li>… and {{ b['items']|length - 5 }} more</li>
            {% endif %}
            </ul>
        </div>
        {% else %}
        <div class="muted" style="margin-top:8px">No items yet.</div>
        {% endif %}

        <div style="margin-top:6px">
          <a href="/b/{{ b.id }}" class="btn secondary">Open (public)</a>
          <a href="/boxes/{{ b.id }}" class="btn secondary no-print">Edit</a>
          <a href="/qr/{{ b.id }}.png" class="btn secondary no-print">Label (2×1)</a>
        </div>
      </div>
      <img src="/qr/{{ b.id }}.png?style=qr&size=120" alt="qr">
    </div>
  </div>
{% endfor %}

<div class="card no-print">
  <form action="/import" method="post" enctype="multipart/form-data" class="row">
    {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
    <input type="file" name="file" accept=".json" required>
    <button class="btn">Import JSON</button>
  </form>
</div>
{% endblock %}
""")

seed("box_public.html", """
{% extends "layout.html" %}
{% block content %}
<h1>{{ box.name }}</h1>
<p class="muted">Location: {{ box.location or "—" }}</p>
{% if box['items'] and box['items']|length > 0 %}
  <ul>
    {% for it in box['items'] %}
      <li>{{ it.name }} ×{{ it.qty }}</li>
    {% endfor %}
  </ul>
{% else %}
  <p>No items listed yet.</p>
{% endif %}
{% endblock %}
""")

seed("box_admin.html", """
{% extends "layout.html" %}
{% block content %}
<h1>Edit: {{ box['name'] }}</h1>
<p class="muted">ID: {{ box['id'] }} | Location: {{ box['location'] or "—" }}</p>

<!-- Edit box name/location -->
<div class="card no-print">
  <form action="/boxes/update" method="post" class="row">
    <input type="hidden" name="box_id" value="{{ box['id'] }}">
    <input name="name" type="text" value="{{ box['name'] }}" required>
    <input name="location" type="text" value="{{ box['location'] or '' }}" placeholder="Location (optional)">
    {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
    <button class="btn">Save Box</button>
  </form>
</div>

<!-- Delete box (requires typing DELETE) -->
<div class="card no-print">
  <form action="/boxes/delete" method="post" class="row">
    <input type="hidden" name="box_id" value="{{ box['id'] }}">
    {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
    <input name="confirm" type="text" placeholder='Type "DELETE" to confirm' required>
    <button class="btn secondary" style="background:#ef4444;color:white;border-color:#ef4444">Delete Box</button>
  </form>
</div>

<!-- Add new item -->
<div class="card no-print">
  <form action="/items" method="post" class="row">
    <input type="hidden" name="box_id" value="{{ box['id'] }}">
    <input name="name" type="text" placeholder="Item name" required>
    <input name="qty" type="number" min="1" value="1" required>
    {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
    <button class="btn">Add Item</button>
  </form>
</div>

<!-- Edit/delete existing items -->
<h3>Items</h3>
{% if box['items'] and box['items']|length > 0 %}
  <div class="card">
    <ul style="list-style:none;padding:0;margin:0">
      {% for it in box['items'] %}
        <li style="margin:6px 0">
          <form action="/items/update" method="post" class="row" style="gap:6px">
            <input type="hidden" name="box_id" value="{{ box['id'] }}">
            <input type="hidden" name="idx" value="{{ loop.index0 }}">
            <input name="name" type="text" value="{{ it.name }}" required>
            <input name="qty" type="number" min="1" value="{{ it.qty }}" required>
            {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
            <button class="btn">Update</button>
          </form>
          <form action="/items/delete" method="post" class="row no-print" style="gap:6px;margin-top:4px">
            <input type="hidden" name="box_id" value="{{ box['id'] }}">
            <input type="hidden" name="idx" value="{{ loop.index0 }}">
            {% if pin_required %}<input name="pin" type="text" placeholder="Admin PIN" required>{% endif %}
            <button class="btn secondary" style="background:#ef4444;color:white;border-color:#ef4444">Delete</button>
          </form>
        </li>
      {% endfor %}
    </ul>
  </div>
{% else %}
  <p>No items yet.</p>
{% endif %}
{% endblock %}
""")

seed("labels.html", """
{% extends "layout.html" %}
{% block content %}
<h1>Printable QR Sheet</h1>
<p class="muted no-print">Tip: Print this page from your browser. For label sheets, adjust margins if needed.</p>
<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(220px,1fr));gap:16px">
  {% for b in boxes %}
    <div style="border:1px solid #eee;border-radius:12px;padding:10px;break-inside:avoid">
      <img src="/qr/{{ b.id }}.png?style=label" alt="qr" style="width:100%">
      <div style="text-align:center;margin-top:6px;font-weight:600">{{ b.name }}</div>
    </div>
  {% endfor %}
</div>
{% endblock %}
""")

# ----------------------------- Helpers -------------------------------------
FONT = ImageFont.load_default()

def make_qr_square(url: str, scale: int = 4) -> Image.Image:
    qr = qrcode.QRCode(border=1, box_size=scale)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("L")

def make_label_2x1(name: str, url: str) -> Image.Image:
    # 384x192 px → 2x1 inches @192 DPI (common thermal label size). Works fine for on-screen too.
    img = Image.new("L", (384, 192), 255)
    qr = make_qr_square(url, scale=3).resize((160, 160))
    img.paste(qr, (10, 16))
    ImageDraw.Draw(img).text((200, 60), name[:22], font=FONT, fill=0)
    return img

def require_pin(pin: Optional[str]) -> None:
    if ADMIN_PIN and pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="Invalid PIN")

# ----------------------------- Routes --------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(r: Request):
    d = load_data()
    return templates.TemplateResponse(
        "index.html",
        {"request": r, "boxes": d["boxes"], "pin_required": bool(ADMIN_PIN)}
    )

from typing import Optional
import re

@app.post("/boxes")
def add_box(
    name: str = Form(...),
    location: str = Form(""),
    items: str = Form(""),                 # NEW
    pin: Optional[str] = Form(None)
):
    require_pin(pin)
    d = load_data()

    # Parse "items" textarea: supports "Name,Qty" or "Name x Qty" (× also ok)
    parsed_items = []
    for line in items.splitlines():
        line = line.strip()
        if not line:
            continue
        qty = 1
        name_part = line

        # Try "name,qty"
        if "," in line:
            left, right = line.rsplit(",", 1)
            name_part = left.strip()
            try:
                qty = int(right.strip())
            except ValueError:
                qty = 1
        else:
            # Try "name x qty" or "name × qty"
            m = re.search(r"(.+?)[x×]\s*(\d+)$", line, flags=re.IGNORECASE)
            if m:
                name_part = m.group(1).strip()
                qty = int(m.group(2))

        if name_part:
            parsed_items.append({"name": name_part, "qty": qty})

    b = {
        "id": uuid.uuid4().hex,
        "name": name.strip(),
        "location": location.strip(),
        "items": parsed_items,             
    }
    d["boxes"].insert(0, b)
    save_data(d)
    return RedirectResponse("/", status_code=303)


@app.get("/b/{bid}", response_class=HTMLResponse)
def box_public(bid: str, r: Request):
    d = load_data()
    b = find_box(d, bid)
    if not b:
        raise HTTPException(404)
    return templates.TemplateResponse("box_public.html", {"request": r, "box": b})

@app.get("/boxes/{bid}", response_class=HTMLResponse)
def box_admin(bid: str, r: Request):
    d = load_data()
    b = find_box(d, bid)
    if not b:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "box_admin.html",
        {"request": r, "box": b, "pin_required": bool(ADMIN_PIN)}
    )

@app.post("/items")
def add_item(
    box_id: str = Form(...),
    name: str = Form(...),
    qty: int = Form(1),
    pin: Optional[str] = Form(None)
):
    require_pin(pin)
    d = load_data()
    b = find_box(d, box_id)
    if not b:
        raise HTTPException(404)
    b.setdefault("items", []).append({"name": name.strip(), "qty": int(qty)})
    save_data(d)
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)

@app.get("/labels", response_class=HTMLResponse)
def labels(r: Request):
    d = load_data()
    return templates.TemplateResponse("labels.html", {"request": r, "boxes": d["boxes"]})

@app.get("/qr/{bid}.png")
def qr_png(bid: str, style: str = "label", size: int = 200):
    d = load_data()
    b = find_box(d, bid)
    if not b:
        raise HTTPException(404)
    url = f"{BASE_URL}/b/{bid}"

    if style == "qr":
        img = make_qr_square(url, scale=max(2, size // 40))
    else:
        img = make_label_2x1(b["name"], url)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")

@app.get("/export")
def export_json():
    content = DATA_FILE.read_bytes() if DATA_FILE.exists() else json.dumps(EMPTY).encode()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="boxes.json"'}
    )

@app.post("/import")
def import_json(file: UploadFile = File(...), pin: Optional[str] = Form(None)):
    require_pin(pin)
    payload = json.loads(file.file.read().decode("utf-8"))
    if "boxes" not in payload or not isinstance(payload["boxes"], list):
        raise HTTPException(400, "Invalid JSON (expected {'boxes': [...]})")
    save_data(payload)
    return RedirectResponse("/", status_code=303)


@app.post("/boxes/update")
def update_box(
    box_id: str = Form(...),
    name: str = Form(...),
    location: str = Form(""),
    pin: Optional[str] = Form(None)
):
    require_pin(pin)
    d = load_data()
    b = find_box(d, box_id)
    if not b:
        raise HTTPException(404)
    b["name"] = name.strip()
    b["location"] = location.strip()
    save_data(d)
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)

# --- Permanently delete a box ---
@app.post("/boxes/delete")
def delete_box(
    box_id: str = Form(...),
    confirm: str = Form(...),      # must be "DELETE"
    pin: Optional[str] = Form(None)
):
    require_pin(pin)
    if confirm.strip().upper() != "DELETE":
        raise HTTPException(400, 'Type "DELETE" to confirm')
    d = load_data()
    before = len(d["boxes"])
    d["boxes"] = [bx for bx in d["boxes"] if bx["id"] != box_id]
    if len(d["boxes"]) == before:
        raise HTTPException(404)
    save_data(d)
    return RedirectResponse("/", status_code=303)

# --- Update an item (by index) ---
@app.post("/items/update")
def update_item(
    box_id: str = Form(...),
    idx: int = Form(...),
    name: str = Form(...),
    qty: int = Form(...),
    pin: Optional[str] = Form(None)
):
    require_pin(pin)
    d = load_data()
    b = find_box(d, box_id)
    if not b:
        raise HTTPException(404)
    items = b.setdefault("items", [])
    if idx < 0 or idx >= len(items):
        raise HTTPException(400, "Invalid item index")
    items[idx] = {"name": name.strip(), "qty": max(1, int(qty))}
    save_data(d)
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)

# --- Delete an item (by index) ---
@app.post("/items/delete")
def delete_item(
    box_id: str = Form(...),
    idx: int = Form(...),
    pin: Optional[str] = Form(None)
):
    require_pin(pin)
    d = load_data()
    b = find_box(d, box_id)
    if not b:
        raise HTTPException(404)
    items = b.setdefault("items", [])
    if idx < 0 or idx >= len(items):
        raise HTTPException(400, "Invalid item index")
    items.pop(idx)
    save_data(d)
    return RedirectResponse(f"/boxes/{box_id}", status_code=303)


# ----------------------------- Entrypoint -----------------------------------
if __name__ == "__main__":
    import uvicorn, textwrap
    print(textwrap.dedent(f"""
    -----------------------------------------
      Server bind: http://0.0.0.0:{PORT}
      BASE_URL   : {BASE_URL}
      Admin PIN? : {'yes' if ADMIN_PIN else 'no'}
      Data file  : {DATA_FILE}
      Note: QR links will point to BASE_URL.
            With localhost, they work on this device only.
    -----------------------------------------
    """))
    uvicorn.run("garage_boxes:app", host="0.0.0.0", port=PORT)
