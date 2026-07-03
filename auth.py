import hmac
import logging
import streamlit as st
from config import CSS

_LOG_CONFIG = dict(
    level=logging.WARNING,
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
try:
    logging.basicConfig(filename='/var/log/finanzas-auth.log', **_LOG_CONFIG)
except OSError:
    # Can't write to /var/log (e.g. non-root deploy) — fall back to stderr
    # instead of crashing the whole app at import time.
    logging.basicConfig(**_LOG_CONFIG)


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
            # compare_digest is constant-time, so response timing leaks nothing
            # about how many leading characters of the guess were correct.
            if hmac.compare_digest(password.encode(), str(st.secrets["password"]).encode()):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                logging.warning(f'Authentication failure from {_get_client_ip()}')
                st.error("Contraseña incorrecta.")
    return False
