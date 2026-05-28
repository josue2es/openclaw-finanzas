# openclaw-finanzas

A personal finance dashboard built on **Streamlit + SQLite**, designed to run alongside an [OpenClaw](https://openclaw.dev) instance on the same server. Track income, expenses, installment plans, recurring subscriptions, and savings — all from a clean, password-protected web UI.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.30%2B-red)
![SQLite](https://img.shields.io/badge/database-sqlite-lightgrey)

---

## Features

| Tab | What you get |
|---|---|
| 📊 **Resumen** | Monthly KPIs (income, expenses, cash balance, card balance) with vs-prior-month deltas + 6 charts |
| 📋 **Transacciones** | Add / edit / delete entries; full-text search; filter by person, category, payment method, amount |
| 🔄 **Recurrentes** | Installment plans (plazo fijo) and perpetual subscriptions with optional auto-pay via cron |
| 🏦 **Ahorros** | Savings account balances with bar and donut charts |

**Also:**
- Cash vs card split across all KPIs
- Amounts are sign-aware: expenses are negative, income positive — charts handle this automatically
- Auth failure logging compatible with fail2ban

---

## Requirements

- Python 3.10+
- An OpenClaw installation (provides the workspace directory)
- Dependencies: `pip install streamlit pandas plotly`

---

## Deployment alongside OpenClaw

### 1. Clone into your OpenClaw workspace

```bash
git clone https://github.com/josue2es/openclaw-finanzas.git \
  ~/.openclaw/workspace/scripts/finanzas_streamlit
```

### 2. Initialize the database

```bash
python3 ~/.openclaw/workspace/scripts/init_finanzas_db.py
```

This creates the database at `~/.openclaw/workspace/finanzas.db` — right inside your existing OpenClaw workspace — and populates default categories and payment methods.

> **Customize first:** Edit `init_finanzas_db.py` before running to replace the default bank cards with your own payment methods.

The `planes_pago` and `cuotas_pago` tables are created automatically on first dashboard launch.

### 3. Configure the DB path

Edit `config.py`:

```python
DB_PATH = Path("/home/YOUR_USER/.openclaw/workspace/finanzas.db")
```

### 4. Set the password

```bash
mkdir -p ~/.openclaw/workspace/scripts/finanzas_streamlit/.streamlit
cat > ~/.openclaw/workspace/scripts/finanzas_streamlit/.streamlit/secrets.toml << 'EOF'
password = "your-password-here"
EOF
chmod 600 ~/.openclaw/workspace/scripts/finanzas_streamlit/.streamlit/secrets.toml
```

### 5. Run

```bash
cd ~/.openclaw/workspace/scripts/finanzas_streamlit
streamlit run streamlit_app.py --server.headless true
```

Dashboard available at `http://your-server:8501`.

---

## Auto-start with systemd (recommended)

Create `/etc/systemd/system/finanzas.service`:

```ini
[Unit]
Description=Finanzas Dashboard (Streamlit)
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/.openclaw/workspace/scripts/finanzas_streamlit
ExecStart=/home/YOUR_USER/.local/bin/streamlit run streamlit_app.py --server.headless true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now finanzas
sudo systemctl status finanzas
```

---

## Brute-force protection with fail2ban

The app writes failed login attempts to `/var/log/finanzas-auth.log`.

**Create the log file:**
```bash
sudo touch /var/log/finanzas-auth.log
sudo chown YOUR_USER:YOUR_USER /var/log/finanzas-auth.log
```

**Create `/etc/fail2ban/filter.d/finanzas.conf`:**
```ini
[Definition]
failregex = ^Authentication failure from <HOST>$
ignoreregex =
datepattern = %%Y-%%m-%%d %%H:%%M:%%S
```

**Add to `/etc/fail2ban/jail.local`:**
```ini
[finanzas]
enabled  = true
port     = 8501
filter   = finanzas
logpath  = /var/log/finanzas-auth.log
maxretry = 3
bantime  = 86400
```

```bash
sudo systemctl restart fail2ban
fail2ban-client status finanzas
```

> **IP resolution note:** If Streamlit runs without a reverse proxy, failed logins may be logged with IP `unknown`. Put nginx in front and pass `X-Forwarded-For` to resolve real client IPs.

---

## Recurring payments & auto-pay (cron)

In the **Recurrentes** tab you can create two types of plans:

- **Plazo fijo** — a purchase split over N months (e.g. a 12-month appliance installment)
- **Recurrente** — a perpetual subscription that auto-renews each month when paid

Checking **🤖 Auto-pago** on a recurrente plan lets a cron job register the payment silently each month without needing to open the dashboard.

Set up the cron job to call your OpenClaw auto-payment script daily — it reads all active `recurrente` plans with `auto_pago = 1` and marks the current month's cuota as paid when the due date arrives.

---

## Directory structure

```
finanzas_streamlit/
├── streamlit_app.py        # Entry point — page config, tabs, main wiring
├── config.py               # DB path, classification constants, chart theme
├── data.py                 # All DB reads/writes, sidebar filter logic
├── views.py                # Tab content: KPIs, transactions table, plans, savings
├── charts.py               # Six Plotly chart functions
├── auth.py                 # Password check + auth failure logging
└── .streamlit/
    └── secrets.toml        # Dashboard password — never committed
```

The database file is intentionally outside this directory:

```
~/.openclaw/
└── workspace/
    ├── finanzas.db                   ← shared database
    └── scripts/
        ├── init_finanzas_db.py       ← first-time setup
        └── finanzas_streamlit/       ← this repo
```

---

## Data model reference

### `transacciones`

The core table. Each row is one financial entry.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `fecha` | TEXT | ISO date string (`YYYY-MM-DD`) |
| `monto` | REAL | **Negative = expense, Positive = income** |
| `clasificacion` | TEXT | See classification values below |
| `descripcion` | TEXT | Free text |
| `quien` | TEXT | Person (e.g. "Josue", "Daniela") |
| `tipo_abono_id` | INTEGER FK | → `tipos_abono.id` |
| `categoria_id` | INTEGER FK | → `categorias.id` |
| `sheet_ref` | TEXT | Optional reference to the source spreadsheet row |

`cargar_datos()` resolves FKs via JOIN and adds a computed column `mes_año` (`YYYY-MM`) derived from `fecha`.

### Classification values

| Value | Sign |
|---|---|
| `Gasto` | negative |
| `Gasto Recurrente` | negative |
| `Ajuste de Gastos` | negative |
| `Ingreso` | positive |
| `Ingreso Recurrente` | positive |
| `Ajuste de Ingresos` | positive |

### `tipos_abono`

Lookup table for payment methods.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `nombre` | TEXT | Display name (e.g. "Efectivo", "Visa Débito") |
| `tipo` | TEXT | Broad category (e.g. `"efectivo"`, `"tarjeta"`) |
| `alias` | TEXT | Short unique alias |
| `activo` | INTEGER | `1` = visible in forms; `0` = hidden |

### `categorias`

Lookup table for expense/income categories.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `nombre` | TEXT | Category name |
| `activo` | INTEGER | `1` = visible in forms; `0` = hidden |

### `planes_pago`

One row per installment plan or recurring subscription.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `nombre` | TEXT | Plan name |
| `monto_total` | REAL | Total amount (used for `plazo_fijo`; `0` for `recurrente`) |
| `num_cuotas` | INTEGER | Number of payments (`0` for `recurrente`) |
| `monto_cuota` | REAL | Amount per payment |
| `dia_cobro` | INTEGER | Day-of-month the payment is due |
| `fecha_inicio` | TEXT | ISO date of first payment |
| `tipo_abono_id` | INTEGER FK | → `tipos_abono.id` |
| `categoria_id` | INTEGER FK | → `categorias.id` |
| `clasificacion` | TEXT | See classification values above |
| `quien` | TEXT | Person this plan belongs to |
| `tipo` | TEXT | `'plazo_fijo'` or `'recurrente'` |
| `auto_pago` | INTEGER | `1` = cron registers payment automatically; `0` = manual |
| `activo` | INTEGER | `0` = cancelled (rows are never deleted) |

### `cuotas_pago`

One row per scheduled payment per plan.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `plan_id` | INTEGER FK | → `planes_pago.id` |
| `num_cuota` | INTEGER | Payment number within the plan |
| `fecha_programada` | TEXT | ISO date the payment is scheduled for |
| `fecha_pago` | TEXT | ISO date the payment was made (`NULL` if unpaid) |
| `transaccion_id` | INTEGER FK | → `transacciones.id` (set when paid) |

For `recurrente` plans: only one pending row exists at a time — when paid, the next month's row is auto-generated.

### `ahorros`

Manually maintained savings account balances.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `nombre` | TEXT | Account name |
| `banco` | TEXT | Bank name |
| `tipo_cuenta` | TEXT | Account type (e.g. "Ahorro", "Corriente") |
| `saldo` | REAL | Current balance |
| `fecha_actualizacion` | TEXT | ISO date of last manual update |
