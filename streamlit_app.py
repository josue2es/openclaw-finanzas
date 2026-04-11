"""
Dashboard de Finanzas Personales — entry point.
Run with: streamlit run finanzas_dashboard.py
"""

import streamlit as st

import os

from config import CSS, COLORS, DB_PATH
from auth import check_auth
from data import cargar_datos, sidebar_filtros, aplicar_filtros, init_planes_tables
from charts import (
    grafica_metodo_pago,
    grafica_metodo_pago_tipo,
    grafica_ingresos_vs_egresos,
    grafica_egresos_por_categoria,
    grafica_tendencia_mensual,
    grafica_top_categorias,
)
from views import mostrar_kpis, tabla_transacciones, seccion_ahorros, seccion_recurrentes

st.set_page_config(
    page_title="Finanzas · Josue",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    st.markdown(CSS, unsafe_allow_html=True)

    if not check_auth():
        st.stop()

    if not DB_PATH.exists():
        st.error(f"Base de datos no encontrada: `{DB_PATH}`")
        st.stop()

    # Ensure planes_pago / cuotas_pago tables exist and all migrations are applied.
    init_planes_tables()

    # Pass mtime as a cache key: cargar_datos is @st.cache_data, so Streamlit only
    # re-queries SQLite when the file was modified since the last call.
    db_mtime = os.path.getmtime(DB_PATH)
    df_todas, ahorros = cargar_datos(db_mtime)
    periodos, quien, tipo = sidebar_filtros(df_todas)
    df = aplicar_filtros(df_todas, periodos, quien, tipo)

    if df.empty:
        st.warning("No hay datos para los filtros seleccionados.")
        st.stop()

    col_title, col_info = st.columns([3, 1])
    with col_title:
        st.markdown("## 💰 Dashboard de Finanzas")
    with col_info:
        muted = COLORS["muted"]
        st.markdown(f"<p style='color:{muted};font-size:0.8rem;"
                    f"text-align:right;padding-top:12px'>"
                    f"{len(df):,} transacciones · {len(periodos)} periodo(s)</p>",
                    unsafe_allow_html=True)

    tab_resumen, tab_detalle, tab_ahorros, tab_recurrentes = st.tabs([
        "📊  Resumen", "📋  Transacciones", "🏦  Ahorros", "🔄  Recurrentes"
    ])

    with tab_resumen:
        mostrar_kpis(df, ahorros, df_todas)
        st.markdown("<br>", unsafe_allow_html=True)

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.plotly_chart(grafica_metodo_pago(df), width="stretch")
        with col_m2:
            st.plotly_chart(grafica_metodo_pago_tipo(df), width="stretch")

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(grafica_ingresos_vs_egresos(df), width="stretch")
        with col2:
            st.plotly_chart(grafica_egresos_por_categoria(df), width="stretch")

        col3, col4 = st.columns(2)
        with col3:
            fig_tend = grafica_tendencia_mensual(df)
            if fig_tend:
                st.plotly_chart(fig_tend, width="stretch")
        with col4:
            st.plotly_chart(grafica_top_categorias(df), width="stretch")

    with tab_detalle:
        tabla_transacciones(df_todas, df)

    with tab_ahorros:
        seccion_ahorros(ahorros)

    with tab_recurrentes:
        seccion_recurrentes()


if __name__ == "__main__":
    main()
