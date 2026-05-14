import calendar
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import streamlit as st

from config import (DB_PATH, CLASIFICACION_INGRESO, CLASIFICACION_EGRESO,
                    CLASIFICACION_AJUSTE, TIPO_RECURRENTE, TIPO_PLAZO_FIJO)


def _add_months(d, n):
    """Add n months to date d, clamping day to end of month when needed.

    Without clamping, adding 1 month to Jan 31 would produce Feb 31 — invalid.
    calendar.monthrange returns (weekday_of_1st, days_in_month), so [1] gives the cap.
    """
    month = d.month + n
    year  = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@contextmanager
def _db():
    """Open a DB connection, commit on success, always close, then clear Streamlit cache.

    The cache clear lives OUTSIDE try/finally intentionally: if an exception is raised
    inside the `with _db()` block the commit is skipped (DB unchanged), so there is
    nothing stale to evict.  The close() in `finally` ensures no connection leak even
    when the caller's code raises.
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
    st.cache_data.clear()


@contextmanager
def _db_read():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        yield conn
    finally:
        conn.close()


def init_planes_tables():
    """Create installment-plan tables if they don't exist, and run one-time migrations.

    Called on every app start (cheap: SQLite no-ops the CREATE IF NOT EXISTS).
    Migrations use a try/except instead of IF NOT EXISTS because ALTER TABLE and
    DROP COLUMN have no conditional syntax in SQLite — the OperationalError signals
    that the migration was already applied in a prior run, so we silently skip it.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS planes_pago (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre        TEXT    NOT NULL,
            monto_total   REAL    NOT NULL DEFAULT 0,
            num_cuotas    INTEGER NOT NULL DEFAULT 0,
            monto_cuota   REAL    NOT NULL,
            dia_cobro     INTEGER NOT NULL,
            fecha_inicio  TEXT    NOT NULL,
            tipo_abono_id INTEGER,
            categoria_id  INTEGER,
            clasificacion TEXT    NOT NULL DEFAULT 'Gasto Recurrente',
            quien         TEXT,
            activo        INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(tipo_abono_id) REFERENCES tipos_abono(id),
            FOREIGN KEY(categoria_id)  REFERENCES categorias(id)
        );
        CREATE TABLE IF NOT EXISTS cuotas_pago (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id          INTEGER NOT NULL,
            num_cuota        INTEGER NOT NULL,
            fecha_programada TEXT    NOT NULL,
            fecha_pago       TEXT,
            transaccion_id   INTEGER,
            FOREIGN KEY(plan_id)        REFERENCES planes_pago(id),
            FOREIGN KEY(transaccion_id) REFERENCES transacciones(id)
        );
    """)
    for sql in [
        "ALTER TABLE planes_pago ADD COLUMN tipo TEXT DEFAULT 'plazo_fijo'",
        "ALTER TABLE planes_pago ADD COLUMN auto_pago INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE transacciones DROP COLUMN periodo",
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # already applied
    conn.close()


def crear_plan(nombre, monto_total, num_cuotas, monto_cuota,
               fecha_inicio, tipo_abono_id, categoria_id, clasificacion, quien,
               tipo=TIPO_PLAZO_FIJO, auto_pago=False):
    """Insert plan + generate all cuotas. Recurrente plans get only the first payment.

    For plazo_fijo plans, all N cuotas are inserted up-front via executemany (one round-trip).
    For recurrente plans, only the first cuota is inserted — each subsequent one is created
    in marcar_cuota_pagada() when the previous payment is registered, so the plan stays
    perpetual without pre-generating an unbounded future row list.
    """
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO planes_pago
                (nombre, monto_total, num_cuotas, monto_cuota, dia_cobro,
                 fecha_inicio, tipo_abono_id, categoria_id, clasificacion, quien, tipo, auto_pago)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (nombre, monto_total, num_cuotas, monto_cuota, fecha_inicio.day,
              str(fecha_inicio), tipo_abono_id, categoria_id, clasificacion, quien, tipo,
              1 if auto_pago else 0))
        plan_id = cur.lastrowid
        if tipo == TIPO_RECURRENTE:
            cur.execute(
                "INSERT INTO cuotas_pago (plan_id, num_cuota, fecha_programada) VALUES (?,?,?)",
                (plan_id, 1, str(fecha_inicio)),
            )
        else:
            rows = [(plan_id, i + 1, str(_add_months(fecha_inicio, i)))
                    for i in range(num_cuotas)]
            cur.executemany(
                "INSERT INTO cuotas_pago (plan_id, num_cuota, fecha_programada) VALUES (?,?,?)",
                rows,
            )


@st.cache_data
def cargar_planes():
    with _db_read() as conn:
        return pd.read_sql("""
            SELECT p.*,
                   ta.nombre AS metodo_pago,
                   c.nombre  AS categoria,
                   COUNT(CASE WHEN cu.fecha_pago IS NOT NULL THEN 1 END) AS cuotas_pagadas,
                   MIN(CASE WHEN cu.fecha_pago IS NULL THEN cu.fecha_programada END) AS proxima_cuota
            FROM planes_pago p
            LEFT JOIN tipos_abono  ta ON p.tipo_abono_id = ta.id
            LEFT JOIN categorias    c ON p.categoria_id  = c.id
            LEFT JOIN cuotas_pago  cu ON cu.plan_id      = p.id
            GROUP BY p.id
            ORDER BY p.activo DESC, p.fecha_inicio
        """, conn)


@st.cache_data
def cargar_cuotas():
    """Return all unpaid cuotas from active plans, enriched with plan fields."""
    with _db_read() as conn:
        return pd.read_sql("""
            SELECT cu.id, cu.plan_id, cu.num_cuota, cu.fecha_programada,
                   p.nombre AS plan_nombre, p.monto_cuota, p.num_cuotas,
                   p.categoria_id, p.tipo_abono_id, p.clasificacion, p.quien,
                   p.tipo,
                   ta.nombre AS metodo_pago,
                   c.nombre  AS categoria
            FROM cuotas_pago cu
            JOIN  planes_pago  p  ON cu.plan_id       = p.id
            LEFT JOIN tipos_abono ta ON p.tipo_abono_id = ta.id
            LEFT JOIN categorias   c ON p.categoria_id  = c.id
            WHERE cu.fecha_pago IS NULL AND p.activo = 1
            ORDER BY cu.fecha_programada
        """, conn)


def marcar_cuota_pagada(cuota_id, plan_id, plan_nombre, plan_tipo,
                         num_cuota, num_cuotas, monto_cuota,
                         fecha_pago, fecha_programada,
                         categoria_id, tipo_abono_id, clasificacion, quien):
    """Create a transaction for the payment and link it back.

    Signs the monto based on clasificacion: income plans (e.g. "Ingreso Recurrente")
    record a positive amount; expense plans record negative.  The cuota row is then
    stamped with the actual payment date and the new transaction's ID so we can trace
    back from the plan to the exact transaction that paid it.

    For recurrente plans, after marking the cuota paid the next month's cuota is
    inserted here — keeping exactly one pending row alive per active recurrente plan.
    """
    if plan_tipo == TIPO_RECURRENTE:
        descripcion = f"{plan_nombre} · {str(fecha_pago)[:7]}"
    else:
        descripcion = f"{plan_nombre} · Pago {num_cuota}/{num_cuotas}"
    monto = abs(monto_cuota) if clasificacion == "Ingreso Recurrente" else -abs(monto_cuota)
    with _db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO transacciones
                (fecha, monto, clasificacion, descripcion, quien, categoria_id, tipo_abono_id)
            VALUES (?,?,?,?,?,?,?)
        """, (str(fecha_pago), monto, clasificacion,
              descripcion, quien or "", categoria_id, tipo_abono_id))
        transaccion_id = cur.lastrowid
        cur.execute(
            "UPDATE cuotas_pago SET fecha_pago=?, transaccion_id=? WHERE id=?",
            (str(fecha_pago), transaccion_id, cuota_id),
        )
        if plan_tipo == TIPO_RECURRENTE:
            next_fecha = _add_months(date.fromisoformat(str(fecha_programada)[:10]), 1)
            cur.execute(
                "INSERT INTO cuotas_pago (plan_id, num_cuota, fecha_programada) VALUES (?,?,?)",
                (plan_id, num_cuota + 1, str(next_fecha)),
            )


def cancelar_plan(plan_id):
    with _db() as conn:
        conn.execute("UPDATE planes_pago SET activo=0 WHERE id=?", (plan_id,))


def actualizar_plan_campos(plan_id, monto_cuota, tipo_abono_id, categoria_id, clasificacion, quien):
    """Persist field changes to the plan (affects all future payments)."""
    with _db() as conn:
        conn.execute("""
            UPDATE planes_pago
            SET monto_cuota=?, tipo_abono_id=?, categoria_id=?, clasificacion=?, quien=?
            WHERE id=?
        """, (monto_cuota, tipo_abono_id, categoria_id, clasificacion, quien or "", plan_id))


@st.cache_data
def cargar_datos(db_mtime):  # db_mtime is the file's mtime — Streamlit re-runs the function only when it changes, busting stale cache after any write
    with _db_read() as conn:
        transacciones = pd.read_sql("""
            SELECT
                t.id, t.fecha, t.monto, t.clasificacion,
                t.descripcion, t.quien,
                c.nombre  AS categoria,
                ta.nombre AS metodo_pago,
                ta.tipo   AS tipo_pago
            FROM transacciones t
            LEFT JOIN categorias  c  ON t.categoria_id  = c.id
            LEFT JOIN tipos_abono ta ON t.tipo_abono_id = ta.id
        """, conn)
        ahorros = pd.read_sql("SELECT * FROM ahorros", conn)

    transacciones["fecha"]   = pd.to_datetime(transacciones["fecha"], errors="coerce")
    transacciones["mes_año"] = transacciones["fecha"].dt.to_period("M").astype(str)
    return transacciones, ahorros


def sidebar_filtros(df):
    with st.sidebar:
        st.markdown("## 💰 Finanzas")
        st.divider()

        st.markdown('<p class="section-header">Filtros</p>', unsafe_allow_html=True)

        now = datetime.now()
        current_year  = now.strftime("%Y")
        current_month = now.strftime("%Y-%m")

        all_periodos = sorted(df["mes_año"].dropna().unique(), reverse=True)

        # Year selector — drives the month list below
        years = sorted({p[:4] for p in all_periodos}, reverse=True)
        default_years = [current_year] if current_year in years else (years[:1] if years else [])
        year_sel = st.multiselect("Año", years, default=default_years)

        # Month selector filtered by selected years
        periodos_filtrados = sorted(
            [p for p in all_periodos if (not year_sel or p[:4] in year_sel)],
            reverse=True,
        )
        default_periodo = (
            [current_month] if current_month in periodos_filtrados
            else (periodos_filtrados[:1] if periodos_filtrados else [])
        )
        periodo_sel = st.multiselect("Mes", periodos_filtrados, default=default_periodo)

        quien_opciones = ["Todos"] + sorted(df["quien"].dropna().unique().tolist())
        quien_sel = st.selectbox("Persona", quien_opciones)

        tipo_sel = st.radio("Tipo", ["Todos", "Ingresos", "Gastos", "Ajuste"])

        st.divider()
        if st.button("🔄 Actualizar datos", width="stretch"):
            st.cache_data.clear()
            st.rerun()
        if st.button("🚪 Cerrar sesión", width="stretch"):
            st.session_state["authenticated"] = False
            st.rerun()

    return periodo_sel, quien_sel, tipo_sel


@st.cache_data(ttl=300)
def cargar_catalogos():
    with _db_read() as conn:
        categorias  = pd.read_sql("SELECT id, nombre FROM categorias ORDER BY nombre", conn)
        tipos_abono = pd.read_sql("SELECT id, nombre FROM tipos_abono ORDER BY nombre", conn)
    return categorias, tipos_abono


def agregar_transaccion(fecha, descripcion, monto, clasificacion, categoria_id, tipo_abono_id, quien):
    with _db() as conn:
        conn.execute("""
            INSERT INTO transacciones (fecha, monto, clasificacion, descripcion, quien, categoria_id, tipo_abono_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fecha, monto, clasificacion, descripcion, quien, categoria_id, tipo_abono_id))


def actualizar_transaccion(id, fecha, descripcion, monto, clasificacion, categoria_id, tipo_abono_id, quien):
    with _db() as conn:
        conn.execute("""
            UPDATE transacciones
            SET fecha=?, monto=?, clasificacion=?, descripcion=?, quien=?, categoria_id=?, tipo_abono_id=?
            WHERE id=?
        """, (fecha, monto, clasificacion, descripcion, quien, categoria_id, tipo_abono_id, id))


def eliminar_transacciones(ids):
    with _db() as conn:
        conn.execute(
            f"DELETE FROM transacciones WHERE id IN ({','.join(['?']*len(ids))})", ids
        )


def aplicar_filtros(df, periodos, quien, tipo):
    if periodos:
        df = df[df["mes_año"].isin(periodos)]
    if quien != "Todos":
        df = df[df["quien"] == quien]
    if tipo == "Ingresos":
        df = df[df["clasificacion"].isin(CLASIFICACION_INGRESO)]
    elif tipo == "Gastos":
        df = df[df["clasificacion"].isin(CLASIFICACION_EGRESO)]
    elif tipo == "Ajuste":
        df = df[df["clasificacion"].isin(CLASIFICACION_AJUSTE)]
    return df
