"""Nexo dashboard (Streamlit, Spanish). The HITL approval inbox is the spine.

No page is reachable without authentication. Every figure shown comes from the
deterministic core; model prose is visibly secondary. Approving an action records the
decision immutably — it does not send anything (execution seam disabled).
"""

from __future__ import annotations

from decimal import Decimal

import streamlit as st
import streamlit_authenticator as stauth

from nexo_os.agents.specialists import all_agents
from nexo_os.audit import AuditWriter, verify_chain
from nexo_os.config import get_settings
from nexo_os.data.factory import get_repository
from nexo_os.data.models import AccionEstado, Prioridad
from nexo_os.i18n import AGENTES, NAV, SIN_DATOS, fmt_ars, fmt_pct
from nexo_os.orchestrator import run_cycle
from nexo_os.review import resolve_accion
from nexo_os.security import users as user_store
from nexo_os.state import NexoContext

settings = get_settings()


@st.cache_resource
def _repo():
    return get_repository()


def _compute_all(repo) -> dict:
    ctx = NexoContext(repo=repo, run_id="display", snapshot_fecha=repo.snapshot_fecha)
    return {a.id: a.compute(ctx) for a in all_agents()}


# ------------------------------------------------------------------ auth --------


def _authenticate():
    creds = user_store.to_authenticator_credentials()
    if not creds["usernames"]:
        st.error(
            "No hay usuarios. Ejecutá `python -m nexo_os bootstrap-admin` con "
            "NEXO_ADMIN_PASSWORD definido en `.env`."
        )
        st.stop()
    authenticator = stauth.Authenticate(
        creds,
        settings.auth_cookie_name,
        settings.auth_cookie_key,
        max(1, settings.auth_session_minutes // 1440),
    )
    try:
        authenticator.login(location="main")
    except Exception as exc:  # pragma: no cover - UI path
        st.error(str(exc))
    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Usuario o contraseña incorrectos.")
        st.stop()
    if status is None:
        st.info("Ingresá tus credenciales para continuar.")
        st.stop()
    return authenticator, st.session_state.get("username"), st.session_state.get("name")


# ------------------------------------------------------------------ views -------


def _view_overview(repo, results) -> None:
    st.header(NAV["overview"])
    st.caption(f"Fuente: {repo.data_source} · Fecha de corte: {repo.snapshot_fecha}")
    car = results["cartera"]
    mor = results["morosidad"]
    com = results["comisiones"]
    pipe = results["pipeline"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Pólizas vigentes", car.polizas_vigentes)
    c2.metric("Prima total", fmt_ars(car.prima_total_ars))
    c3.metric("Comisión esperada", fmt_ars(car.comision_esperada_ars))

    c4, c5, c6 = st.columns(3)
    c4.metric("Mora (ARS)", fmt_ars(mor.total_vencido_ars))
    c5.metric(
        "Tasa de morosidad",
        fmt_pct(mor.tasa_morosidad_ars) if mor.tasa_morosidad_ars is not None else SIN_DATOS,
    )
    c6.metric("Cobranza pendiente", fmt_ars(mor.total_vencido_ars))

    c7, c8, c9 = st.columns(3)
    c7.metric("Pipeline abierto", fmt_ars(pipe.open_value_ars))
    c8.metric("Comisiones por cobrar", fmt_ars(com.receivable_vencido_ars))
    c9.metric("Diferencias de comisión", fmt_ars(com.diferencia_total_ars))

    st.divider()
    st.caption(
        "Todos los números provienen del núcleo determinista. "
        "Las recomendaciones en texto son secundarias a las cifras."
    )


def _view_agent(repo, results, agent_id: str) -> None:
    st.header(AGENTES.get(agent_id, agent_id))
    result = results[agent_id]
    # headline figures (dataclass fields that are simple scalars)
    figs = {
        k: v
        for k, v in vars(result).items()
        if k != "hallazgos" and isinstance(v, (int, Decimal, str, type(None)))
    }
    if figs:
        cols = st.columns(min(4, len(figs)) or 1)
        for i, (k, v) in enumerate(figs.items()):
            disp = fmt_ars(v) if isinstance(v, Decimal) else (SIN_DATOS if v is None else str(v))
            cols[i % len(cols)].metric(k, disp)

    st.subheader("Hallazgos")
    rows = [
        {
            "entidad": f"{h.entidad_tipo}:{h.entidad_id}",
            "monto_en_juego": fmt_ars(h.monto_en_juego_ars),
            "urgencia_dias": h.urgencia_dias if h.urgencia_dias is not None else SIN_DATOS,
            **{k: str(v) for k, v in h.numeros.items()},
        }
        for h in getattr(result, "hallazgos", [])
    ]
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.info("Sin hallazgos para este agente en esta corrida.")


def _view_inbox(repo, username: str) -> None:
    st.header(NAV["inbox"])
    st.caption(
        "La aprobación registra la decisión de forma inmutable. No envía ni ejecuta "
        "nada hacia sistemas externos en esta versión."
    )
    acciones = repo.get_acciones(estado=AccionEstado.propuesta)
    if not acciones:
        st.info("No hay acciones propuestas. Corré el análisis desde la barra lateral.")
        return

    prio_rank = {Prioridad.alta: 0, Prioridad.media: 1, Prioridad.baja: 2}
    acciones.sort(
        key=lambda a: (prio_rank[a.prioridad], -(float(a.monto_en_juego_ars or 0))),
    )
    audit = AuditWriter(repo)
    st.write(f"**{len(acciones)}** acciones pendientes.")
    for a in acciones:
        amount = fmt_ars(a.monto_en_juego_ars)
        with st.expander(
            f"[{a.prioridad.value.upper()}] {AGENTES.get(a.agente, a.agente)} · "
            f"{a.tipo_accion} · {amount} · confianza {a.confianza:.2f}"
        ):
            st.markdown(f"**Recomendación:** {a.mensaje_es or SIN_DATOS}")
            st.caption("Rationale determinista (las cifras):")
            st.json(a.rationale_json)
            nota = st.text_input("Nota del revisor (opcional)", key=f"nota_{a.accion_id}")
            editado = st.text_input(
                "Mensaje editado (para 'Editar')", key=f"edit_{a.accion_id}", value=a.mensaje_es
            )
            b1, b2, b3 = st.columns(3)
            if b1.button("Aprobar", key=f"ap_{a.accion_id}"):
                resolve_accion(repo, audit, a.accion_id, AccionEstado.aprobada, username, nota)
                st.success("Aprobada y registrada.")
                st.rerun()
            if b2.button("Rechazar", key=f"re_{a.accion_id}"):
                resolve_accion(repo, audit, a.accion_id, AccionEstado.rechazada, username, nota)
                st.warning("Rechazada y registrada.")
                st.rerun()
            if b3.button("Editar", key=f"ed_{a.accion_id}"):
                resolve_accion(
                    repo, audit, a.accion_id, AccionEstado.editada, username, nota, editado
                )
                st.info("Editada y registrada.")
                st.rerun()


def _view_audit(repo) -> None:
    st.header(NAV["audit"])
    events = repo.get_audit_events()
    chk = verify_chain(events)
    if chk.ok:
        st.success(f"Cadena de auditoría íntegra ({chk.total} eventos).")
    else:
        st.error(f"Cadena de auditoría ROTA en el evento #{chk.broken_at}.")
    rows = [
        {
            "ts": e.ts.isoformat(timespec="seconds"),
            "actor": e.actor,
            "accion": e.accion,
            "entidad": f"{e.entidad_tipo}:{e.entidad_id or ''}",
            "hash": e.hash[:12],
        }
        for e in reversed(events)
    ]
    st.dataframe(rows, width="stretch") if rows else st.info("Sin eventos.")


# ------------------------------------------------------------------ main --------


def main() -> None:
    st.set_page_config(page_title="Nexo", page_icon="🛡️", layout="wide")
    authenticator, username, name = _authenticate()
    role = user_store.get_role(username) or user_store.ROLE_OPERADOR
    repo = _repo()

    with st.sidebar:
        st.title("Nexo")
        st.caption("Co-piloto de la corredora")
        st.write(f"**{name}** · {role}")
        authenticator.logout(location="sidebar")
        st.divider()
        st.caption(f"Corte: {repo.snapshot_fecha} · {repo.data_source}")
        if st.button("Correr análisis", type="primary"):
            with st.spinner("Calculando..."):
                ctx = run_cycle(repo=repo)
            st.success(f"{len(ctx.acciones)} acciones propuestas.")
        st.divider()
        nav_options = (
            [NAV["overview"]]
            + [AGENTES[a] for a in AGENTES]
            + [
                NAV["inbox"],
                NAV["audit"],
            ]
        )
        if role == user_store.ROLE_ADMIN:
            nav_options.append("Usuarios")
        choice = st.radio("Vista", nav_options, label_visibility="collapsed")

    results = _compute_all(repo)
    agent_by_name = {AGENTES[a]: a for a in AGENTES}

    if choice == NAV["overview"]:
        _view_overview(repo, results)
    elif choice in agent_by_name:
        _view_agent(repo, results, agent_by_name[choice])
    elif choice == NAV["inbox"]:
        _view_inbox(repo, username)
    elif choice == NAV["audit"]:
        _view_audit(repo)
    elif choice == "Usuarios":
        st.header("Usuarios")
        st.caption("Gestión de seats (solo admin).")
        st.dataframe(
            [
                {"usuario": u, "nombre": i["name"], "rol": i.get("role")}
                for u, i in user_store.load_users().get("usernames", {}).items()
            ],
            width="stretch",
        )


if __name__ == "__main__":
    main()
