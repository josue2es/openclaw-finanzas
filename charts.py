import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import COLORS, CHART_LAYOUT, CHART_LAYOUT_PIE, CLASIFICACION_INGRESO, CLASIFICACION_EGRESO


# 1 - Egresos por Tipo de Pago y Categoría
def grafica_metodo_pago(df):
    # The double filter (clasificacion + monto < 0) is intentional: "Ajuste de Gastos"
    # rows can appear in CLASIFICACION_EGRESO but sometimes carry positive amounts (reversals).
    # Requiring monto < 0 ensures only actual outflows are charted.
    egresos = df[(df["clasificacion"].isin(CLASIFICACION_EGRESO)) & (df["monto"] < 0)].copy()
    egresos["monto"] = egresos["monto"].abs()

    # Sort ascending so that Plotly (bottom-to-top) renders the largest bar at the top
    totals = egresos.groupby("metodo_pago")["monto"].sum().sort_values(ascending=True)
    orden  = totals.index.tolist()

    fig = px.bar(
        egresos, x="monto", y="metodo_pago", color="categoria",
        orientation="h",
        barmode="stack",
        title="1 - Egresos por Tipo de Pago y Categoría",
        labels={"monto": "Total ($)", "metodo_pago": "", "categoria": "Categoría"},
        category_orders={"metodo_pago": orden},
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_layout(**CHART_LAYOUT)
    fig.update_traces(marker_line_width=0)
    # Plotly stacked bars don't show a grand total automatically — add one annotation
    # per bar at its right edge so the reader sees the full spend per payment method.
    for metodo, total in totals.items():
        fig.add_annotation(
            x=total, y=metodo,
            text=f"${total:,.0f}",
            xanchor="left", showarrow=False,
            font=dict(size=11, color="white"),
            xshift=6,
        )
    return fig


# 2 - Balance por Tipo de Pago
def grafica_metodo_pago_tipo(df):
    balance = df.groupby("metodo_pago")["monto"].sum().reset_index()
    balance = balance.sort_values("monto", ascending=True)
    colors  = balance["monto"].apply(lambda v: COLORS["ingreso"] if v >= 0 else COLORS["egreso"]).tolist()

    fig = go.Figure(go.Bar(
        x=balance["monto"],
        y=balance["metodo_pago"],
        orientation="h",
        marker_color=colors,
        marker_line_width=0,
        text=balance["monto"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
    ))
    fig.update_layout(title="2 - Balance por Tipo de Pago", xaxis_title="Balance ($)", **CHART_LAYOUT)
    return fig


# 3 - Ingresos vs Gastos por Periodo
def grafica_ingresos_vs_egresos(df):
    ing = df[df["clasificacion"].isin(CLASIFICACION_INGRESO)].groupby("mes_año")["monto"].sum().reset_index()
    ing["tipo"] = "Ingresos"
    gas = df[(df["clasificacion"].isin(CLASIFICACION_EGRESO)) & (df["monto"] < 0)].groupby("mes_año")["monto"].sum().abs().reset_index()
    gas["tipo"] = "Gastos"
    resumen = pd.concat([ing, gas])
    fig = px.bar(
        resumen, x="mes_año", y="monto", color="tipo",
        barmode="group",
        color_discrete_map={"Ingresos": COLORS["ingreso"], "Gastos": COLORS["egreso"]},
        title="3 - Ingresos vs Gastos por Periodo",
        labels={"monto": "Monto ($)", "mes_año": "", "tipo": ""},
    )
    fig.update_layout(**CHART_LAYOUT, legend_title_text="")
    fig.update_traces(marker_line_width=0, opacity=0.9,
                      texttemplate="$%{y:,.0f}", textposition="outside")
    return fig


# 4 - Egresos por Categoría
def grafica_egresos_por_categoria(df):
    egresos = df[(df["clasificacion"].isin(CLASIFICACION_EGRESO)) & (df["monto"] < 0)]
    por_cat = egresos.groupby("categoria")["monto"].sum().abs().reset_index()
    fig = px.pie(
        por_cat, values="monto", names="categoria",
        title="4 - Egresos por Categoría",
        hole=0.55,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_traces(textposition="outside", textinfo="percent+label")
    fig.update_layout(**CHART_LAYOUT_PIE)
    return fig


# 5 - Balance Neto Mensual
def grafica_tendencia_mensual(df):
    ing = df[df["clasificacion"].isin(CLASIFICACION_INGRESO)].groupby("mes_año")["monto"].sum().rename("ingreso")
    gas = df[(df["clasificacion"].isin(CLASIFICACION_EGRESO)) & (df["monto"] < 0)].groupby("mes_año")["monto"].sum().abs().rename("egreso")
    # concat on axis=1 aligns by mes_año index; fillna(0) handles months that have
    # only income or only expenses so subtraction doesn't produce NaN.
    mensual = pd.concat([ing, gas], axis=1).fillna(0).reset_index()
    if mensual.empty:
        return None

    mensual["balance"] = mensual["ingreso"] - mensual["egreso"]
    mensual = mensual.sort_values("mes_año")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=mensual["mes_año"], y=mensual["balance"],
        mode="lines+markers",
        line=dict(color=COLORS["neutro"], width=2.5),
        marker=dict(size=7, color=COLORS["neutro"], line=dict(color="#0f172a", width=2)),
        fill="tozeroy",
        fillcolor="rgba(99,102,241,0.12)",
        name="Balance",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["border"], opacity=0.7)
    fig.update_layout(title="5 - Balance Neto Mensual",
                      xaxis_title="", yaxis_title="Balance ($)",
                      showlegend=False, **CHART_LAYOUT)
    return fig


# 6 - Top Categorías de Gasto
def grafica_top_categorias(df):
    egresos = df[(df["clasificacion"].isin(CLASIFICACION_EGRESO)) & (df["monto"] < 0)]
    top = (
        egresos.groupby("categoria")["monto"]
        .sum().abs().sort_values(ascending=False).head(8).reset_index()
    )
    fig = px.bar(
        top, x="monto", y="categoria", orientation="h",
        title="6 - Top Categorías de Gasto",
        labels={"monto": "Total ($)", "categoria": ""},
        color="monto",
        color_continuous_scale=[[0, "#7f1d1d"], [1, COLORS["egreso"]]],
    )
    fig.update_layout(**CHART_LAYOUT, coloraxis_showscale=False)
    fig.update_layout(yaxis=dict(categoryorder="total ascending", gridcolor=COLORS["border"]))
    fig.update_traces(marker_line_width=0,
                      text=top["monto"], texttemplate="$%{x:,.0f}",
                      textposition="outside")
    return fig
