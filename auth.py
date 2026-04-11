import logging
import streamlit as st
from config import CSS

logging.basicConfig(
    filename='/var/log/finanzas-auth.log',
    level=logging.WARNING,
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)


def _get_client_ip() -> str:
    """Extract the real client IP from request headers for fail2ban logging.

    Priority: X-Forwarded-For (nginx/proxy sets this) → X-Real-Ip (alternative proxy header)
    → "unknown" (direct Streamlit without a reverse proxy).
    X-Forwarded-For can contain a comma-separated chain when there are multiple proxies;
    we take the first entry, which is the original client.
    The outer try/except guards against Streamlit versions where st.context is unavailable.
    """
    try:
        headers = st.context.headers
        return (headers.get("X-Forwarded-For") or headers.get("X-Real-Ip") or "unknown").split(",")[0].strip()
    except Exception:
        return "unknown"


def check_auth() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.markdown(CSS, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("""
        <div class="login-card">
            <div class="login-title">💰 Finanzas</div>
            <div class="login-sub">Panel de control personal</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        password = st.text_input("Contraseña", type="password", key="pwd_input",
                                  placeholder="Ingresa tu contraseña")
        if st.button("Entrar →", width="stretch"):
            if password == st.secrets["password"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                logging.warning(f'Authentication failure from {_get_client_ip()}')
                st.error("Contraseña incorrecta.")
    return False
