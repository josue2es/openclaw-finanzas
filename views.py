from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from config import (CHART_LAYOUT, CHART_LAYOUT_PIE, CLASIFICACION_INGRESO, CLASIFICACION_EGRESO,
                    METODOS_EFECTIVO, TIPO_RECURRENTE, TIPO_PLAZO_FIJO)
from data import (cargar_catalogos, agregar_transaccion, actualizar_transaccion,
                  eliminar_transacciones, cargar_planes, cargar_cuotas,
                  crear_plan, marcar_cuota_pagada, cancelar_plan, actualizar_plan_campos)

CLASIFICACIONES           = ["Gasto", "Ingreso", "Ajuste de Gastos", "Ajuste de Ingresos"]
CLASIFICACIONES_RECURRENTES = ["Gasto Recurrente", "Ingreso Recurrente"]

# Income classifications that produce a positive monto when entered
_CLASIFICACION_POSITIVA = set(CLASIFICACION_INGRESO)

# Columns searched by the free-text filter in the transactions table
_SEARCH_COLS = ["descripcion", "categoria", "metodo_pago", "quien", "clasificacion"]


def _lookup_id(df, nombre):
    """Return the integer ID for the row where df['nombre'] == nombre."""
    return int(df.loc[df["nombre"] == nombre, "id"].iloc[0])


def _pago_label(r):
    """Human-readable label for a cuota row: '∞' for recurrentes, 'Pago N/T' for plazo fijo."""
    if str(r.get("tipo", "")) == TIPO_RECURRENTE:
        return "∞"
    return f"Pago {int(r['num_cuota'])}/{int(r['num_cuotas'])}"


def mostrar_kpis(df, ahorros, df_todas=None):
    df_cash = df[df["metodo_pago"].isin(METODOS_EFECTIVO)]
    df_card = df[~df["metodo_pago"].isin(METODOS_EFECTIVO)]

    total_ingresos = df_cash[df_cash["monto"] > 0]["monto"].sum()
    total_egresos  = abs(df_cash[df_cash["monto"] < 0]["monto"].sum())
    balance        = df_cash["monto"].sum()
    card_balance   = df_card["monto"].sum()

    # Compute previous-period deltas (only when a single month is selected)
    delta_ingresos = delta_egresos = delta_balance = delta_card = None
    if df_todas is not None and not df.empty:
        periodos_sel = sorted(df["mes_año"].dropna().unique())
        if len(periodos_sel) == 1:
            periodo_actual = periodos_sel[0]
            all_periodos   = sorted(df_todas["mes_año"].dropna().unique())
            idx = list(all_periodos).index(periodo_actual) if periodo_actual in all_periodos else -1
            if idx > 0:
                periodo_prev = all_periodos[idx - 1]
                df_prev      = df_todas[df_todas["mes_año"] == periodo_prev]
                df_prev_cash = df_prev[df_prev["metodo_pago"].isin(METODOS_EFECTIVO)]
                df_prev_card = df_prev[~df_prev["metodo_pago"].isin(METODOS_EFECTIVO)]
                delta_ingresos = total_ingresos - df_prev_cash[df_prev_cash["monto"] > 0]["monto"].sum()
                delta_egresos  = total_egresos  - abs(df_prev_cash[df_prev_cash["monto"] < 0]["monto"].sum())
                delta_balance  = balance        - df_prev_cash["monto"].sum()
                delta_card     = card_balance   - df_prev_card["monto"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💵 Ingresos",    f"${total_ingresos:,.2f}",
              delta=round(delta_ingresos, 2) if delta_ingresos is not None else None,
              delta_color="normal",  delta_description="vs. mes anterior")
    c2.metric("💸 Gastos",      f"${total_egresos:,.2f}",
              delta=round(delta_egresos, 2)  if delta_egresos  is not None else None,
              delta_color="inverse", delta_description="vs. mes anterior")
    c3.metric("⚖️ Cash Balance", f"${balance:,.2f}",
              delta=round(delta_balance, 2)  if delta_balance  is not None else None,
              delta_color="normal",  delta_description="vs. mes anterior")
    c4.metric("💳 Card Balance", f"${card_balance:,.2f}",
              delta=round(delta_card, 2)     if delta_card     is not None else None,
              delta_color="normal",  delta_description="vs. mes anterior")


def _form_transaccion(key, categorias, tipos_abono, defaults=None):
    """Renders add/edit form fields. Returns (fecha, descripcion, monto, clasificacion, categoria_id, tipo_abono_id, quien)."""
    d = defaults or {}
    cat_nombres   = categorias["nombre"].tolist()
    abono_nombres = tipos_abono["nombre"].tolist()

    fecha         = st.date_input("Fecha", value=d.get("fecha", date.today()), key=f"fecha_{key}")
    descripcion   = st.text_input("Descripción", value=d.get("descripcion", ""), key=f"desc_{key}")
    monto_raw     = st.number_input("Monto", value=abs(float(d.get("monto", 0.0))), min_value=0.0, step=0.01, key=f"monto_{key}")
    clasificacion = st.selectbox("Clasificación", CLASIFICACIONES,
                                  index=CLASIFICACIONES.index(d["clasificacion"]) if d.get("clasificacion") in CLASIFICACIONES else 0,
                                  key=f"clas_{key}")
    cat_idx   = cat_nombres.index(d["categoria"])    if d.get("categoria")    in cat_nombres   else 0
    abono_idx = abono_nombres.index(d["metodo_pago"]) if d.get("metodo_pago") in abono_nombres else 0
    categoria_nombre  = st.selectbox("Categoría",      cat_nombres,   index=cat_idx,   key=f"cat_{key}")
    tipo_abono_nombre = st.selectbox("Método de pago", abono_nombres, index=abono_idx, key=f"abono_{key}")
    quien = st.text_input("Quién", value=d.get("quien", ""), key=f"quien_{key}")

    monto = abs(monto_raw) if clasificacion in _CLASIFICACION_POSITIVA else -abs(monto_raw)
    return str(fecha), descripcion, monto, clasificacion, _lookup_id(categorias, categoria_nombre), _lookup_id(tipos_abono, tipo_abono_nombre), quien


def tabla_transacciones(df_full, df):
    """df_full = unfiltered (for edit/delete selectors), df = filtered for display."""
    categorias, tipos_abono = cargar_catalogos()

    busqueda = st.text_input("🔍 Buscar en todas las columnas",
                              placeholder="descripción, categoría, método de pago…",
                              label_visibility="collapsed")

    with st.expander("🔧 Filtros avanzados"):
        c1, c2, c3 = st.columns(3)
        with c1:
            f_quien = st.multiselect("Quién",
                sorted(df["quien"].dropna().unique()))
        with c2:
            f_clasificacion = st.multiselect("Clasificación",
                sorted(df["clasificacion"].dropna().unique()))
            f_categoria = st.multiselect("Categoría",
                sorted(df["categoria"].dropna().unique()))
        with c3:
            f_metodo = st.multiselect("Método de pago",
                sorted(df["metodo_pago"].dropna().unique()))
            monto_min = float(df["monto"].min())
            monto_max = float(df["monto"].max())
            # Slider requires a non-zero range; skip it when all amounts are equal
            if monto_min < monto_max:
                f_monto = st.slider("Rango de monto",
                    min_value=monto_min, max_value=monto_max,
                    value=(monto_min, monto_max), format="$%.0f")
            else:
                f_monto = None

    if busqueda:
        # Vectorized search across text columns — avoids row-by-row Python iteration
        mask = pd.concat(
            [df[c].astype(str).str.contains(busqueda, case=False, na=False) for c in _SEARCH_COLS],
            axis=1,
        ).any(axis=1)
        df = df[mask]

    if f_quien:
        df = df[df["quien"].isin(f_quien)]
    if f_clasificacion:
        df = df[df["clasificacion"].isin(f_clasificacion)]
    if f_categoria:
        df = df[df["categoria"].isin(f_categoria)]
    if f_metodo:
        df = df[df["metodo_pago"].isin(f_metodo)]
    if f_monto is not None:
        df = df[(df["monto"] >= f_monto[0]) & (df["monto"] <= f_monto[1])]

    st.caption(f"{len(df):,} transacciones")

    df_display = df[["id", "fecha", "descripcion", "categoria",
                      "monto", "clasificacion", "metodo_pago", "quien"]].copy()
    df_display["fecha"] = df_display["fecha"].dt.strftime("%Y-%m-%d")

    st.dataframe(
        df_display.sort_values("fecha", ascending=False),
        width="stretch",
        hide_index=True,
        height=400,
        column_config={
            "id":            st.column_config.NumberColumn("ID", width=60),
            "fecha":         st.column_config.TextColumn("Fecha", width=100),
            "descripcion":   st.column_config.TextColumn("Descripción"),
            "categoria":     st.column_config.TextColumn("Categoría", width=130),
            "monto":         st.column_config.NumberColumn("Monto", format="$%.2f", width=110),
            "clasificacion": st.column_config.TextColumn("Tipo", width=90),
            "metodo_pago":   st.column_config.TextColumn("Método", width=130),
            "quien":         st.column_config.TextColumn("Quién", width=90),
        }
    )

    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("➕ Agregar transacción"):
        with st.form("form_agregar", clear_on_submit=True):
            fecha, descripcion, monto, clasificacion, categoria_id, tipo_abono_id, quien = \
                _form_transaccion("add", categorias, tipos_abono)
            if st.form_submit_button("Guardar", width="stretch"):
                agregar_transaccion(fecha, descripcion, monto, clasificacion, categoria_id, tipo_abono_id, quien)
                st.success("Transacción agregada.")
                st.rerun()

    # Sort once — reused by both edit and delete option builders below
    df_sorted = df_full.sort_values("fecha", ascending=False)

    with st.expander("✏️ Editar transacción"):
        opciones = {
            f"{row['id']} · {str(row['fecha'])[:10]} · {row['descripcion']}": row
            for _, row in df_sorted.iterrows()
        }
        seleccion = st.selectbox("Seleccionar transacción", list(opciones.keys()), index=None, key="edit_sel")
        if seleccion:
            row    = opciones[seleccion]
            row_id = int(row["id"])
            defaults = {
                "fecha":         row["fecha"].date() if hasattr(row["fecha"], "date") else row["fecha"],
                "descripcion":   row["descripcion"],
                "monto":         row["monto"],
                "clasificacion": row["clasificacion"],
                "categoria":     row["categoria"],
                "metodo_pago":   row["metodo_pago"],
                "quien":         row["quien"],
            }
            # Key includes row_id so widgets are recreated fresh on each selection change
            with st.form(f"form_editar_{row_id}"):
                fecha, descripcion, monto, clasificacion, categoria_id, tipo_abono_id, quien = \
                    _form_transaccion(f"edit_{row_id}", categorias, tipos_abono, defaults)
                if st.form_submit_button("Guardar cambios", width="stretch"):
                    actualizar_transaccion(row_id, fecha, descripcion, monto,
                                           clasificacion, categoria_id, tipo_abono_id, quien)
                    st.success("Transacción actualizada.")
                    st.rerun()

    with st.expander("🗑️ Eliminar transacciones"):
        opciones_del = {
            f"{row['id']} · {str(row['fecha'])[:10]} · {row['descripcion']}": int(row["id"])
            for _, row in df_sorted.iterrows()
        }
        seleccionadas = st.multiselect("Seleccionar transacciones a eliminar", list(opciones_del.keys()))
        if seleccionadas:
            st.warning(f"Se eliminarán {len(seleccionadas)} transacción(es). Esta acción no se puede deshacer.")
            if st.button("🗑️ Confirmar eliminación", type="primary"):
                ids = [opciones_del[s] for s in seleccionadas]
                eliminar_transacciones(ids)
                st.success(f"{len(ids)} transacción(es) eliminada(s).")
                st.rerun()


def seccion_ahorros(ahorros):
    total = ahorros["saldo"].sum()
    st.metric("💰 Total en ahorros", f"${total:,.2f}")
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            ahorros.sort_values("saldo", ascending=False),
            x="nombre", y="saldo", color="banco",
            title="Saldo por Cuenta",
            labels={"saldo": "Saldo ($)", "nombre": ""},
            text_auto="$.2f",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig.update_layout(**CHART_LAYOUT)
        fig.update_traces(marker_line_width=0, textposition="outside", textfont=dict(size=11))
        st.plotly_chart(fig, width="stretch")

    with col2:
        fig2 = px.pie(
            ahorros, values="saldo", names="nombre",
            title="Distribución de Ahorros",
            hole=0.5,
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig2.update_layout(**CHART_LAYOUT_PIE)
        st.plotly_chart(fig2, width="stretch")

    st.dataframe(
        ahorros[["nombre", "banco", "tipo_cuenta", "saldo", "fecha_actualizacion"]],
        width="stretch",
        hide_index=True,
        column_config={
            "nombre":              st.column_config.TextColumn("Cuenta"),
            "banco":               st.column_config.TextColumn("Banco"),
            "tipo_cuenta":         st.column_config.TextColumn("Tipo"),
            "saldo":               st.column_config.NumberColumn("Saldo", format="$%.2f"),
            "fecha_actualizacion": st.column_config.TextColumn("Actualizado"),
        }
    )


def seccion_recurrentes():
    planes  = cargar_planes()
    activos = planes[planes["activo"] == 1].copy()
    cuotas  = cargar_cuotas()
    categorias, tipos_abono = cargar_catalogos()

    hoy = date.today()

    egresos_activos    = activos[activos["clasificacion"] != "Ingreso Recurrente"]
    compromiso_mensual = float(egresos_activos["monto_cuota"].sum()) if not egresos_activos.empty else 0.0
    pendientes         = len(cuotas)
    proxima            = cuotas["fecha_programada"].min() if not cuotas.empty else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💳 Compromiso mensual", f"${compromiso_mensual:,.2f}")
    k2.metric("📋 Planes activos",     len(activos))
    k3.metric("📅 Pagos pendientes",   pendientes)
    k4.metric("⏰ Próximo pago",       str(proxima)[:10] if proxima else "—")

    st.markdown("<br>", unsafe_allow_html=True)

    if not activos.empty:
        recurrentes = activos[activos["tipo"] == TIPO_RECURRENTE].copy()
        fijos       = activos[activos["tipo"] != TIPO_RECURRENTE].copy()

        if not recurrentes.empty:
            st.markdown("### Recurrentes")
            disp = recurrentes[["nombre", "monto_cuota", "metodo_pago", "proxima_cuota", "auto_pago"]].copy()
            disp["proxima_cuota"] = disp["proxima_cuota"].apply(lambda v: str(v)[:10] if v else "—")
            disp["auto_pago"]     = disp["auto_pago"].astype(bool)
            st.dataframe(
                disp, width="stretch", hide_index=True,
                column_config={
                    "nombre":        st.column_config.TextColumn("Plan"),
                    "monto_cuota":   st.column_config.NumberColumn("Mensual", format="$%.2f", width=110),
                    "metodo_pago":   st.column_config.TextColumn("Método", width=140),
                    "proxima_cuota": st.column_config.TextColumn("Próximo pago", width=120),
                    "auto_pago":     st.column_config.CheckboxColumn("🤖 Auto", width=70),
                },
            )

        if not fijos.empty:
            st.markdown("### Plazo fijo")
            for _, plan in fijos.iterrows():
                pagadas      = int(plan["cuotas_pagadas"])
                total        = int(plan["num_cuotas"])
                pct          = pagadas / total if total else 0.0
                proxima_plan = str(plan["proxima_cuota"])[:10] if plan["proxima_cuota"] else "—"

                col_info, col_bar = st.columns([3, 2])
                with col_info:
                    st.markdown(
                        f"**{plan['nombre']}** &nbsp;·&nbsp; "
                        f"${plan['monto_cuota']:,.2f}/mes &nbsp;·&nbsp; "
                        f"{plan['metodo_pago'] or '—'}",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"Pago {pagadas}/{total} &nbsp;·&nbsp; "
                        f"Próximo: {proxima_plan} &nbsp;·&nbsp; "
                        f"Total compra: ${plan['monto_total']:,.2f}"
                    )
                with col_bar:
                    st.progress(pct, text=f"{pagadas}/{total} ({pct*100:.0f}%)")
                st.markdown("---")
    else:
        st.info("No hay planes de pago activos.")

    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("✅ Registrar pago"):
        if cuotas.empty:
            st.info("No hay pagos pendientes.")
        else:
            opciones = {
                f"{r['plan_nombre']} · {_pago_label(r)} · {str(r['fecha_programada'])[:10]} · ${r['monto_cuota']:,.2f}": r
                for _, r in cuotas.iterrows()
            }
            sel = st.selectbox("Pago a registrar", list(opciones.keys()), key="reg_sel")
            r   = opciones[sel]
            ck  = str(int(r["id"]))  # unique key per cuota — resets widgets on selection change

            cat_nombres   = categorias["nombre"].tolist()
            abono_nombres = tipos_abono["nombre"].tolist()
            cat_actual    = str(r["categoria"])   if r["categoria"]   else (cat_nombres[0]   if cat_nombres   else "")
            abono_actual  = str(r["metodo_pago"]) if r["metodo_pago"] else (abono_nombres[0] if abono_nombres else "")

            c1, c2 = st.columns(2)
            with c1:
                fecha_pago = st.date_input("Fecha de pago", value=hoy, key=f"reg_fecha_{ck}")
                monto_edit = st.number_input(
                    "Monto", value=abs(float(r["monto_cuota"])), min_value=0.01, step=0.01,
                    key=f"reg_monto_{ck}",
                )
                _clas_val = str(r["clasificacion"]) if str(r["clasificacion"]) in CLASIFICACIONES_RECURRENTES else CLASIFICACIONES_RECURRENTES[0]
                clas_edit = st.selectbox(
                    "Clasificación", CLASIFICACIONES_RECURRENTES,
                    index=CLASIFICACIONES_RECURRENTES.index(_clas_val),
                    key=f"reg_clas_{ck}",
                )
            with c2:
                cat_edit = st.selectbox(
                    "Categoría", cat_nombres,
                    index=cat_nombres.index(cat_actual) if cat_actual in cat_nombres else 0,
                    key=f"reg_cat_{ck}",
                )
                abono_edit = st.selectbox(
                    "Método de pago", abono_nombres,
                    index=abono_nombres.index(abono_actual) if abono_actual in abono_nombres else 0,
                    key=f"reg_abono_{ck}",
                )
                quien_edit = st.text_input(
                    "Quién", value=str(r["quien"]) if r["quien"] else "",
                    key=f"reg_quien_{ck}",
                )

            plan_tipo = str(r.get("tipo", TIPO_PLAZO_FIJO))
            help_perm = (
                "El próximo pago recurrente usará estos valores."
                if plan_tipo == TIPO_RECURRENTE else
                "Actualiza el plan: todos los pagos restantes usarán estos valores."
            )
            permanent = st.checkbox("💾 Guardar cambios como permanentes", help=help_perm, key=f"reg_perm_{ck}")

            if st.button("✅ Registrar pago", type="primary", key="reg_btn"):
                marcar_cuota_pagada(
                    cuota_id         = int(r["id"]),
                    plan_id          = int(r["plan_id"]),
                    plan_nombre      = r["plan_nombre"],
                    plan_tipo        = plan_tipo,
                    num_cuota        = int(r["num_cuota"]),
                    num_cuotas       = int(r["num_cuotas"]),
                    monto_cuota      = monto_edit,
                    fecha_pago       = fecha_pago,
                    fecha_programada = str(r["fecha_programada"]),
                    categoria_id     = _lookup_id(categorias, cat_edit),
                    tipo_abono_id    = _lookup_id(tipos_abono, abono_edit),
                    clasificacion    = clas_edit,
                    quien            = quien_edit,
                )
                if permanent:
                    actualizar_plan_campos(
                        plan_id       = int(r["plan_id"]),
                        monto_cuota   = monto_edit,
                        tipo_abono_id = _lookup_id(tipos_abono, abono_edit),
                        categoria_id  = _lookup_id(categorias, cat_edit),
                        clasificacion = clas_edit,
                        quien         = quien_edit,
                    )
                st.success("Pago registrado — la transacción fue creada automáticamente.")
                st.rerun()

    with st.expander("➕ Nuevo plan"):
        tipo_sel = st.radio(
            "Tipo de plan", ["Plazo fijo", "Recurrente (sin fecha de fin)"],
            horizontal=True, key="tipo_plan_nuevo",
        )
        es_recurrente = tipo_sel == "Recurrente (sin fecha de fin)"

        with st.form("form_plan", clear_on_submit=True):
            nombre = st.text_input(
                "Nombre",
                placeholder="TV Samsung" if not es_recurrente else "Netflix",
            )
            c1, c2 = st.columns(2)
            with c1:
                if not es_recurrente:
                    monto_total = st.number_input("Monto total de la compra", min_value=0.0, step=0.01)
                    num_cuotas  = st.number_input("Número de cuotas", min_value=1, max_value=120, step=1, value=12)
                else:
                    st.info("Se renueva automáticamente cada mes al registrar el pago.")
                    monto_total = 0.0
                    num_cuotas  = 0
            with c2:
                monto_cuota = st.number_input(
                    "Monto mensual" if es_recurrente else "Monto por cuota",
                    min_value=0.0, step=0.01,
                    help="Monto que se cobra cada mes" if es_recurrente
                         else "Puede diferir de total÷cuotas si hay intereses o cargos",
                )
                fecha_inicio = st.date_input(
                    "Fecha del primer pago" if es_recurrente else "Fecha de la primera cuota",
                    value=hoy,
                )

            c3, c4 = st.columns(2)
            with c3:
                clas_sel = st.selectbox("Clasificación", CLASIFICACIONES_RECURRENTES, index=0)
                cat_sel  = st.selectbox("Categoría", categorias["nombre"].tolist())
            with c4:
                abono_sel = st.selectbox("Método de pago", tipos_abono["nombre"].tolist())
                quien     = st.text_input("Quién")

            if es_recurrente:
                auto_pago = st.checkbox(
                    "🤖 Auto-pago — registrar automáticamente cuando venza (sin notificación)",
                    help="El cron diario pagará este gasto solo. Úsalo para suscripciones fijas como Disney, Netflix, etc."
                )
            else:
                auto_pago = False

            if st.form_submit_button("Crear plan", width="stretch"):
                if not nombre.strip():
                    st.error("El nombre es requerido.")
                elif monto_cuota <= 0:
                    st.error("El monto mensual debe ser mayor a 0.")
                else:
                    tipo_db = TIPO_RECURRENTE if es_recurrente else TIPO_PLAZO_FIJO
                    crear_plan(nombre.strip(), monto_total, int(num_cuotas), monto_cuota,
                               fecha_inicio, _lookup_id(tipos_abono, abono_sel),
                               _lookup_id(categorias, cat_sel), clas_sel, quien, tipo_db, auto_pago)
                    if es_recurrente:
                        st.success(f"Plan recurrente '{nombre.strip()}' creado.")
                    else:
                        st.success(f"Plan '{nombre.strip()}' creado con {int(num_cuotas)} cuotas.")
                    st.rerun()

    if not activos.empty:
        with st.expander("❌ Cancelar plan"):
            opc = {f"{int(r['id'])} · {r['nombre']}": int(r["id"])
                   for _, r in activos.iterrows()}
            sel_c = st.selectbox("Plan a cancelar", list(opc.keys()))
            st.warning("El plan se marcará como cancelado. "
                       "Las cuotas ya pagadas permanecen en transacciones.")
            if st.button("❌ Confirmar cancelación"):
                cancelar_plan(opc[sel_c])
                st.success("Plan cancelado.")
                st.rerun()
