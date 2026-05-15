from pathlib import Path

DB_PATH = Path("/home/hermes/finanzas/finanzas.db")

# ── Transaction classifications ───────────────────────────────────────────────
CLASIFICACION_INGRESO = ["Ingreso Recurrente", "Ingreso", "Ajuste de Ingresos"]
CLASIFICACION_EGRESO  = ["Gasto Recurrente", "Gasto", "Ajuste de Gastos"]
CLASIFICACION_AJUSTE  = [c for c in CLASIFICACION_EGRESO + CLASIFICACION_INGRESO if "Ajuste" in c]

# ── Plan types (match values stored in DB) ────────────────────────────────────
TIPO_RECURRENTE = "recurrente"
TIPO_PLAZO_FIJO = "plazo_fijo"

# ── Sidebar filter options ────────────────────────────────────────────────────
TIPO_OPCIONES = ["Todos", "Ingresos", "Gastos", "Ajuste"]

# ── Transaction classification option lists (used in forms) ───────────────────
CLASIFICACIONES = ["Gasto", "Ingreso", "Ajuste de Gastos", "Ajuste de Ingresos"]
CLASIFICACIONES_RECURRENTES = ["Gasto Recurrente", "Ingreso Recurrente"]

# ── Payment methods counted as cash (not credit card) ─────────────────────────
METODOS_EFECTIVO = {"Efectivo", "Histórico/Efectivo"}

COLORS = {
    "ingreso": "#22c55e",
    "egreso":  "#ef4444",
    "neutro":  "#6366f1",
    "fondo":   "#0f172a",
    "card":    "#1e293b",
    "border":  "#334155",
    "text":    "#e2e8f0",
    "muted":   "#94a3b8",
}

CHART_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color=COLORS["text"], size=13),
    title_font=dict(size=15, color=COLORS["text"]),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"]),
    yaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"]),
)

# Pie/donut charts don't have axes — use this variant to avoid Plotly warnings
CHART_LAYOUT_PIE = {k: v for k, v in CHART_LAYOUT.items() if k not in ("xaxis", "yaxis")}

CSS = """
<style>
[data-testid="stMetric"] {
    border: 1px solid rgba(128,128,128,0.3);
    border-radius: 10px;
    padding: 1rem 1.2rem;
}
</style>
"""
