"""CV / portfolio framing for the public demo (shown only when demo_mode is on).

A recruiter landing on the deployed demo should understand, in 30 seconds, what
the project is and who built it - before diving into the product views. This
module is isolated from the product dashboard and never renders in production
(app.py only wires it under settings.demo_mode).

EDIT the ABOUT dict with your real details. Placeholders are intentional - not
invented.
"""

from __future__ import annotations

import streamlit as st

# --------------------------------------------------------------------------- #
# EDIT ME - your CV header.
# --------------------------------------------------------------------------- #
ABOUT = {
    "nombre": "Ignacio Viola",
    # DRAFT - verificá/ajustá tu título real. Alternativas:
    #   "Software / Data Engineer - IA aplicada, determinismo y auditabilidad"
    #   "Ingeniero de Software - IA aplicada a operaciones"
    "rol": "Ingeniero de Software - sistemas de datos y aplicaciones de IA con humano en el ciclo",
    # DRAFT - cierto y verificable contra este repo; editá a gusto.
    "bio": (
        "Construyo sistemas donde la IA asiste pero las decisiones son auditables: "
        "los numeros se calculan en codigo (deterministas, trazables), el modelo solo "
        "prioriza y redacta, y una persona aprueba cada accion. Nexo es un ejemplo - "
        "un modelo operativo para una correduria de seguros con bandeja human-in-the-loop, "
        "auditoria encadenada por hash y backends de datos intercambiables "
        "(sintetico / BigQuery / GCS)."
    ),
    "email": "ignacioviola1984@gmail.com",
    "github": "https://github.com/ignacioviola1984-spec",
    "github_repo": "https://github.com/ignacioviola1984-spec/nexo-os",
    # Completá con tu URL real de LinkedIn (con el placeholder "[" no se muestra el link).
    "linkedin": "https://www.linkedin.com/in/[tu-perfil]",
}


def render_proyecto(settings, repo) -> None:
    st.header("Nexo Operating Model")
    st.caption(
        f"Demo publica de portfolio · datos 100% sinteticos · corte {repo.snapshot_fecha} "
        f"· fuente {repo.data_source}"
    )
    st.markdown("""
**Que es.** Un sistema de *analytics y accion* para una correduria de seguros en
Argentina. Diez agentes especialistas leen los datos del negocio, calculan el
estado de la cartera de forma **determinista**, marcan lo que necesita atencion y
**proponen acciones que un humano aprueba** antes de darlas por hechas.

**Los tres no-negociables**
- **Todo numero se calcula en codigo**, deterministicamente y trazable a sus
  insumos. El modelo nunca produce, estima ni redondea una cifra: rutea, prioriza
  y redacta prosa en espanol. Si un numero no se puede calcular, lo dice; no lo
  inventa (un *guard de grounding* rechaza cualquier cifra no respaldada).
- **Humano en el ciclo en cada accion.** Los agentes proponen; una persona
  aprueba. Las aprobaciones se registran de forma inmutable.
- **Falla cerrado.** Dato faltante, chequeo fallido o baja confianza -> marca y
  frena; nunca adivina.
        """)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Agentes especialistas", "10")
    c2.metric("Tests", "97")
    c3.metric("Backend de datos", "DuckDB local")
    c4.metric("Secretos para la demo", "0")
    st.markdown("""
**Stack.** Python · pydantic (modelo tipado) · DuckDB (store local) · Streamlit
(tablero) · Anthropic Claude (capa de analisis/prosa, *opcional* con fallback
determinista) · bcrypt (auth) · pytest + ruff/black. Backend opcional BigQuery
para produccion; esta demo corre 100% local con datos sinteticos.

**Arquitectura.** datos -> nucleo determinista (cada cifra) -> 10 agentes
(compute/propose) -> reconciliaciones -> capa de analisis (interpreta, no altera
cifras) -> bandeja HITL (aprobar/editar/rechazar) -> auditoria encadenada por hash.
        """)
    st.info(
        "Esta demo se auto-inicializa con datos ficticios y corrio un ciclo completo "
        "de los 10 agentes. Recorre las vistas en la barra lateral: cada cifra viene "
        "del nucleo determinista, no del modelo."
    )
    st.caption(f"Codigo: {ABOUT['github_repo']}")


def render_perfil(settings, repo) -> None:
    st.header(ABOUT["nombre"])
    st.subheader(ABOUT["rol"])
    st.write(ABOUT["bio"])
    # Show only configured links (skip any value still holding a "[placeholder]").
    links = [
        f"✉️ [{ABOUT['email']}](mailto:{ABOUT['email']})",
        f"💻 [GitHub]({ABOUT['github']})",
    ]
    if "[" not in ABOUT["linkedin"]:
        links.append(f"🔗 [LinkedIn]({ABOUT['linkedin']})")
    cols = st.columns(len(links))
    for col, link in zip(cols, links, strict=True):
        col.markdown(link)
    st.divider()
    st.caption(
        "Edita nexo_os/dashboard/portfolio.py (ABOUT) para completar rol, bio y LinkedIn. "
        "Este perfil solo aparece en la demo publica (demo_mode); el tablero de "
        "produccion no lo muestra."
    )
