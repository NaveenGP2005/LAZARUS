"""
LAZARUS — dashboard.py
Streamlit dashboard. Four tabs: Coroner Report, Recovery Dashboard,
Counterfactual Comparison, Audit Trail.

Run: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import json
import sqlite3
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    ARCHETYPE_LIST, ARCHETYPES, ARCHETYPE_RECOVERY_RATES,
    DB_PATH, TRANSACTIONS_PATH, BATCH_DISTRIBUTION
)
from sandbox import render_sandbox
import plotly.graph_objects as go

# Archetype color palette — matches CSS pills
ARCH_COLORS = {
    "empty_vault":     "#fbbf24",
    "frozen_gate":     "#63c8ff",
    "dropped_signal":  "#34d399",
    "hesitant_hand":   "#fb923c",
    "limit_breaker":   "#a78bfa",
    "expired_mandate": "#f472b6",
    "ghost_checkout":  "#94a3b8",
    "velocity_trap":   "#f87171",
}

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LAZARUS — Cause-Aware Payment Recovery",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.main { background: #0a0e1a; }
.block-container { padding: 1.5rem 2rem; max-width: 1400px; }

/* Header */
.lazarus-header {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a1a2e 50%, #16213e 100%);
    border: 1px solid rgba(99, 200, 255, 0.15);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}
.lazarus-header::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse at 20% 50%, rgba(99, 200, 255, 0.05) 0%, transparent 60%);
}
.lazarus-title {
    font-size: 2.4rem; font-weight: 700; letter-spacing: -0.02em;
    background: linear-gradient(135deg, #63c8ff 0%, #a78bfa 50%, #f472b6 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin: 0; padding: 0;
}
.lazarus-sub {
    color: rgba(255,255,255,0.5); font-size: 0.95rem; margin-top: 0.3rem;
    font-weight: 400; letter-spacing: 0.02em;
}
.track-badge {
    display: inline-block;
    background: rgba(167,139,250,0.15); color: #a78bfa;
    border: 1px solid rgba(167,139,250,0.3);
    padding: 0.2rem 0.8rem; border-radius: 100px;
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em;
    text-transform: uppercase; margin-bottom: 0.8rem;
}

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #0d1b2a, #1a1a2e);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px; padding: 1.2rem 1.5rem;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: rgba(99, 200, 255, 0.25); }
.metric-val { font-size: 2rem; font-weight: 700; color: #63c8ff; font-family: 'JetBrains Mono', monospace; }
.metric-lbl { font-size: 0.8rem; color: rgba(255,255,255,0.45); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.2rem; }
.metric-delta-pos { font-size: 0.85rem; color: #34d399; font-weight: 600; margin-top: 0.3rem; }
.metric-delta-neg { font-size: 0.85rem; color: #f87171; font-weight: 600; margin-top: 0.3rem; }

/* Archetype pills */
.arch-pill {
    display: inline-block; padding: 0.2rem 0.7rem; border-radius: 100px;
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.03em;
}
.arch-empty_vault     { background: rgba(251,191,36,0.12); color: #fbbf24; border: 1px solid rgba(251,191,36,0.25); }
.arch-frozen_gate     { background: rgba(99,200,255,0.12); color: #63c8ff; border: 1px solid rgba(99,200,255,0.25); }
.arch-dropped_signal  { background: rgba(52,211,153,0.12); color: #34d399; border: 1px solid rgba(52,211,153,0.25); }
.arch-hesitant_hand   { background: rgba(251,146,60,0.12); color: #fb923c; border: 1px solid rgba(251,146,60,0.25); }
.arch-limit_breaker   { background: rgba(167,139,250,0.12); color: #a78bfa; border: 1px solid rgba(167,139,250,0.25); }
.arch-expired_mandate { background: rgba(244,114,182,0.12); color: #f472b6; border: 1px solid rgba(244,114,182,0.25); }
.arch-ghost_checkout  { background: rgba(148,163,184,0.12); color: #94a3b8; border: 1px solid rgba(148,163,184,0.25); }
.arch-velocity_trap   { background: rgba(248,113,113,0.12); color: #f87171; border: 1px solid rgba(248,113,113,0.25); }

/* Disclaimer box */
.disclaimer {
    background: rgba(251,191,36,0.06); border: 1px solid rgba(251,191,36,0.2);
    border-radius: 8px; padding: 0.8rem 1.2rem;
    color: rgba(251,191,36,0.8); font-size: 0.8rem; line-height: 1.5;
}

/* Verdict badges */
.verdict-ALLOW  { color: #34d399; font-weight: 700; }
.verdict-BLOCK  { color: #f87171; font-weight: 700; }
.verdict-DEFER  { color: #fbbf24; font-weight: 700; }
.outcome-SUCCESS { color: #34d399; font-weight: 600; }
.outcome-FAILURE { color: #f87171; font-weight: 600; }
.outcome-BLOCKED { color: #94a3b8; font-weight: 600; }
.outcome-DEFERRED { color: #fbbf24; font-weight: 600; }

/* Tab styling */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03); border-radius: 10px; padding: 4px; gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    color: rgba(255,255,255,0.4); border-radius: 8px; padding: 0.5rem 1.2rem;
    font-weight: 500; font-size: 0.9rem;
}
.stTabs [aria-selected="true"] {
    background: rgba(99,200,255,0.12) !important; color: #63c8ff !important;
}

/* Table */
.stDataFrame { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_transactions():
    p = Path(TRANSACTIONS_PATH)
    if not p.exists():
        return []
    with open(p) as f:
        return json.load(f)

@st.cache_data(ttl=5)
def load_audit():
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM lazarus_audit ORDER BY id", conn)
    return df

@st.cache_data
def load_batch_results():
    p = Path("batch_results.json")
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="lazarus-header">
    <div class="track-badge">Track 03 · AI Revenue Recovery</div>
    <div class="lazarus-title">LAZARUS</div>
    <div class="lazarus-sub">Cause-Aware Payment Recovery Agent &nbsp;·&nbsp; Razorpay AI Buildathon 2026</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────
transactions = load_transactions()
audit_df = load_audit()
batch = load_batch_results()

has_audit = not audit_df.empty
has_batch = batch is not None

# ─────────────────────────────────────────────────────────────────────────────
# Top-level KPI row
# ─────────────────────────────────────────────────────────────────────────────

if has_audit:
    total = len(audit_df)
    recovered = (audit_df["outcome"] == "SUCCESS").sum()
    blocked = (audit_df["outcome"] == "BLOCKED").sum()
    recovered_inr = audit_df["recovered_amount_paise"].sum() / 100
    unsafe = len(audit_df[(audit_df["archetype"] == "velocity_trap") & (audit_df["gate_verdict"] != "BLOCK")])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-val">{total}</div>
            <div class="metric-lbl">Transactions Processed</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-val">{recovered}</div>
            <div class="metric-lbl">Recovered</div>
            <div class="metric-delta-pos">{recovered/total:.0%} recovery rate</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-val">₹{recovered_inr:,.0f}</div>
            <div class="metric-lbl">Amount Recovered</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-val">{blocked}</div>
            <div class="metric-lbl">Gate Blocked</div>
            <div class="metric-delta-pos">Compliance enforced</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-val">{unsafe}</div>
            <div class="metric-lbl">Unsafe Actions</div>
            <div class="metric-delta-pos">velocity_trap shielded</div>
        </div>""", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🔬 Coroner's Report",
    "📊 Recovery Dashboard",
    "🧮 Counterfactual Comparison",
    "📋 Audit Trail",
    "🎮 Live Sandbox",
    "🏢 Merchant Intelligence",
    "💬 Chat Simulator"
])

# ──────────────────────────────────────────────────────────
# TAB 1: Coroner's Report
# ──────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Failure Archetype Classification")
    st.markdown("Every failed transaction classified into one of 8 cause-specific archetypes. "
                "Deterministic rule engine for known NPCI codes, Bayesian Network for ambiguous signals.")

    if has_audit:
        arch_counts = audit_df["archetype"].value_counts().reset_index()
        arch_counts.columns = ["Archetype", "Count"]

        col_chart, col_table = st.columns([1, 1])

        with col_chart:
            # Plotly bar chart with per-archetype colours
            counts_map = dict(zip(arch_counts["Archetype"], arch_counts["Count"]))
            fig = go.Figure(go.Bar(
                x=ARCHETYPE_LIST,
                y=[counts_map.get(a, 0) for a in ARCHETYPE_LIST],
                marker_color=[ARCH_COLORS.get(a, "#63c8ff") for a in ARCHETYPE_LIST],
                marker_line_color="rgba(255,255,255,0.06)",
                marker_line_width=1,
                hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
            ))
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="rgba(255,255,255,0.6)", size=11),
                margin=dict(l=0, r=0, t=8, b=0),
                height=320,
                xaxis=dict(showgrid=False, tickangle=-30),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_table:
            st.markdown("**Archetype breakdown with recovery rates**")
            rows = []
            for arch in ARCHETYPE_LIST:
                count = int(arch_counts[arch_counts["Archetype"] == arch]["Count"].sum()) if arch in arch_counts["Archetype"].values else 0
                baseline_r, lazarus_r = ARCHETYPE_RECOVERY_RATES.get(arch, (0, 0))
                cfg = ARCHETYPES[arch]
                rows.append({
                    "Archetype": arch,
                    "Count": count,
                    "Contact Customer": "Yes" if cfg["contact_customer"] else "No",
                    "Baseline Rate": f"{baseline_r:.0%}",
                    "LAZARUS Rate": f"{lazarus_r:.0%}",
                    "Lift": f"+{(lazarus_r - baseline_r):.0%}",
                })
            df_table = pd.DataFrame(rows)
            st.dataframe(df_table, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("**The 8 Failure Archetypes — Domain Model**")
        for arch, cfg in ARCHETYPES.items():
            with st.expander(f"**{arch.replace('_', ' ').title()}** — {cfg['description']}"):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Recovery action:** `{cfg['recovery_action']}`")
                c2.markdown(f"**Customer contact:** `{'Yes' if cfg['contact_customer'] else 'No — silent'}`")
                c3.markdown(f"**Error codes:** `{', '.join(cfg['error_codes'][:3])}{'...' if len(cfg['error_codes']) > 3 else ''}`")
    else:
        st.info("Run `python -X utf8 batch_runner.py` to populate the audit trail.")

    # ── Self-calibrating prior (always shown if audit data exists)
    if has_audit:
        st.markdown("---")
        st.markdown("### 🧠 Self-Calibrating Prior: Domain Model vs Observed")
        st.markdown(
            "Every archetype has a **domain prior** (expected LAZARUS recovery rate from industry data). "
            "Here we compare those priors against **what this batch actually observed**. "
            "Delta shows how well the model is calibrated."
        )
        prior_rows = []
        for arch in ARCHETYPE_LIST:
            prior_bl, prior_lz = ARCHETYPE_RECOVERY_RATES.get(arch, (0, 0))
            arch_rows  = audit_df[audit_df["archetype"] == arch]
            total      = len(arch_rows)
            observed_n = int((arch_rows["outcome"] == "SUCCESS").sum())
            obs_rate   = observed_n / total if total > 0 else None
            if obs_rate is not None:
                delta_pp = (obs_rate - prior_lz) * 100
                flag = "🟢" if abs(delta_pp) <= 10 else ("🟡" if abs(delta_pp) <= 20 else "🔴")
                delta_str = f"{flag} {delta_pp:+.1f}pp"
            else:
                delta_str = "—"
            prior_rows.append({
                "Archetype":            arch,
                "Domain Prior (LAZARUS)": f"{prior_lz:.0%}",
                "Observed Rate":        f"{obs_rate:.0%}" if obs_rate is not None else "—",
                "Delta":               delta_str,
                "N":                   total,
            })
        st.dataframe(pd.DataFrame(prior_rows), hide_index=True, use_container_width=True)
        st.caption(
            "⚠ Observed rates are from a single simulated batch (N=100). "
            "In production, calibrate from thousands of real webhook outcomes. "
            "🟢 = well-calibrated (±10pp) · 🟡 = moderate drift · 🔴 = needs recalibration."
        )

# ──────────────────────────────────────────────────────────
# TAB 2: Recovery Dashboard
# ──────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Recovery Outcomes — LAZARUS vs Baseline")

    if has_batch:
        bl = batch["baseline"]
        lz = batch["lazarus"]

        # Side-by-side headline metrics
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            bl_rate = bl["recovery_rate"]
            lz_rate = lz["recovery_rate"]
            st.metric("Recovery Rate", f"{lz_rate:.0%}", f"+{(lz_rate - bl_rate):.0%} vs baseline")
        with col_b:
            bl_inr = bl["recovered_paise"] / 100
            lz_inr = lz["recovered_paise"] / 100
            st.metric("Amount Recovered", f"₹{lz_inr:,.0f}", f"+₹{lz_inr - bl_inr:,.0f} vs baseline")
        with col_c:
            st.metric("Unsafe Actions", str(lz["unsafe_actions"]),
                      f"{bl['unsafe_actions'] - lz['unsafe_actions']} fewer than baseline", delta_color="inverse")

        st.markdown("---")

        # Per-archetype comparison
        st.markdown("**Per-Archetype: Baseline vs LAZARUS Recovery Rate**")
        rows = []
        for arch in ARCHETYPE_LIST:
            baseline_r, lazarus_r = ARCHETYPE_RECOVERY_RATES.get(arch, (0, 0))
            rows.append({
                "Archetype": arch,
                "Baseline (%)": round(baseline_r * 100, 1),
                "LAZARUS (%)": round(lazarus_r * 100, 1),
                "Lift (pp)": round((lazarus_r - baseline_r) * 100, 1),
            })
        df_comp = pd.DataFrame(rows).set_index("Archetype")
        st.dataframe(df_comp, use_container_width=True)

        # Grouped bar chart — Baseline vs LAZARUS
        st.markdown("**Per-Archetype Recovery Rate: Baseline vs LAZARUS**")
        fig_bar = go.Figure()
        bl_rates = [round(ARCHETYPE_RECOVERY_RATES.get(a, (0,0))[0]*100, 1) for a in ARCHETYPE_LIST]
        lz_rates = [round(ARCHETYPE_RECOVERY_RATES.get(a, (0,0))[1]*100, 1) for a in ARCHETYPE_LIST]
        fig_bar.add_trace(go.Bar(
            name="Baseline", x=ARCHETYPE_LIST, y=bl_rates,
            marker_color="rgba(148,163,184,0.5)",
            hovertemplate="<b>%{x}</b><br>Baseline: %{y}%<extra></extra>",
        ))
        fig_bar.add_trace(go.Bar(
            name="LAZARUS", x=ARCHETYPE_LIST, y=lz_rates,
            marker_color=[ARCH_COLORS.get(a, "#63c8ff") for a in ARCHETYPE_LIST],
            hovertemplate="<b>%{x}</b><br>LAZARUS: %{y}%<extra></extra>",
        ))
        fig_bar.update_layout(
            barmode="group",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="rgba(255,255,255,0.6)", size=11),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=0, t=24, b=0), height=320,
            xaxis=dict(showgrid=False, tickangle=-30),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", title="Recovery Rate (%)"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        # Radar chart — shows shape of advantage across all archetypes
        st.markdown("**Radar: LAZARUS Advantage Profile**")
        categories = [a.replace("_", " ").title() for a in ARCHETYPE_LIST]
        categories_closed = categories + [categories[0]]  # close the polygon
        bl_closed = bl_rates + [bl_rates[0]]
        lz_closed = lz_rates + [lz_rates[0]]
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=bl_closed, theta=categories_closed,
            fill="toself", name="Baseline",
            line_color="rgba(148,163,184,0.6)",
            fillcolor="rgba(148,163,184,0.08)",
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=lz_closed, theta=categories_closed,
            fill="toself", name="LAZARUS",
            line_color="#63c8ff",
            fillcolor="rgba(99,200,255,0.12)",
        ))
        fig_radar.update_layout(
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(visible=True, range=[0, 100], gridcolor="rgba(255,255,255,0.08)",
                                tickfont=dict(color="rgba(255,255,255,0.4)", size=9)),
                angularaxis=dict(gridcolor="rgba(255,255,255,0.08)",
                                 tickfont=dict(color="rgba(255,255,255,0.7)", size=10)),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, bgcolor="rgba(0,0,0,0)",
                        font=dict(color="rgba(255,255,255,0.6)")),
            margin=dict(l=40, r=40, t=20, b=40),
            height=380,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        st.markdown("---")
        st.markdown("**velocity_trap: The case for doing nothing**")
        st.markdown("""
        LAZARUS recovers **0%** of velocity_trap transactions — intentionally.
        The baseline "recovers" 2% by retrying despite the fraud flag. That 2% creates chargeback exposure.
        LAZARUS blocks all actions and escalates to the merchant. **Revenue preservation here means
        not creating liability, not recovering the transaction.**
        """)

        # ── Sankey: full transaction flow
        if has_audit:
            st.markdown("---")
            st.markdown("**Transaction Flow: Archetype → Compliance Gate → Outcome**")
            st.caption("Each ribbon shows how transactions flow through the pipeline. Width = volume. Read left to right.")

            VERDICT_LABELS  = ["ALLOW", "DEFER", "BLOCK"]
            OUTCOME_LABELS  = ["SUCCESS", "FAILURE", "DEFERRED", "BLOCKED"]
            VERDICT_COLORS  = {"ALLOW": "#34d399", "DEFER": "#fbbf24", "BLOCK": "#f87171"}
            OUTCOME_COLORS  = {"SUCCESS": "#34d399", "FAILURE": "#f87171",
                               "DEFERRED": "#fbbf24", "BLOCKED": "#94a3b8"}

            all_labels = ARCHETYPE_LIST + VERDICT_LABELS + OUTCOME_LABELS
            all_colors = (
                [ARCH_COLORS.get(a, "#94a3b8") for a in ARCHETYPE_LIST]
                + [VERDICT_COLORS[v] for v in VERDICT_LABELS]
                + [OUTCOME_COLORS[o] for o in OUTCOME_LABELS]
            )

            def hex_to_rgba(hex_str, opacity=0.33):
                h = hex_str.lstrip('#')
                r = int(h[0:2], 16)
                g = int(h[2:4], 16)
                b = int(h[4:6], 16)
                return f"rgba({r}, {g}, {b}, {opacity})"

            sources, targets, values, link_colors = [], [], [], []

            for (arch, verdict), cnt in audit_df.groupby(["archetype","gate_verdict"]).size().items():
                if arch in ARCHETYPE_LIST and verdict in VERDICT_LABELS:
                    sources.append(ARCHETYPE_LIST.index(arch))
                    targets.append(len(ARCHETYPE_LIST) + VERDICT_LABELS.index(verdict))
                    values.append(int(cnt))
                    link_colors.append(hex_to_rgba(ARCH_COLORS.get(arch, "#94a3b8"), 0.3))

            for (verdict, outcome), cnt in audit_df.groupby(["gate_verdict","outcome"]).size().items():
                if verdict in VERDICT_LABELS and outcome in OUTCOME_LABELS:
                    sources.append(len(ARCHETYPE_LIST) + VERDICT_LABELS.index(verdict))
                    targets.append(len(ARCHETYPE_LIST) + len(VERDICT_LABELS) + OUTCOME_LABELS.index(outcome))
                    values.append(int(cnt))
                    link_colors.append(hex_to_rgba(VERDICT_COLORS.get(verdict, "#94a3b8"), 0.3))

            fig_sankey = go.Figure(go.Sankey(
                node=dict(
                    pad=20, thickness=18,
                    label=all_labels,
                    color=all_colors,
                    line=dict(color="rgba(0,0,0,0)", width=0),
                ),
                link=dict(source=sources, target=targets, value=values, color=link_colors),
            ))
            fig_sankey.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="rgba(255,255,255,0.75)", size=11),
                margin=dict(l=0, r=0, t=8, b=0),
                height=430,
            )
            st.plotly_chart(fig_sankey, use_container_width=True)
    else:
        st.info("Run `python -X utf8 batch_runner.py` to generate comparison data.")

# ──────────────────────────────────────────────────────────
# TAB 3: Counterfactual Comparison
# ──────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Model-Based Counterfactual Estimate")
    st.markdown("""
    For each archetype, we ask: *what would the expected recovery have been if we had used the
    generic baseline strategy instead?* This uses our domain-informed causal model to estimate
    the intervention lift.
    """)

    st.markdown("""<div class="disclaimer">
    <strong>⚠ Disclaimer:</strong> These are model-based estimates derived from domain-informed priors,
    not experimentally proven causal effects. The priors are constructed from industry knowledge about
    UPI/card failure recovery rates. For production deployment, calibrate with A/B test data.
    </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if has_batch:
        cf = batch["lazarus"].get("counterfactual_summary", {})

        c1, c2, c3 = st.columns(3)
        with c1:
            bl_exp = cf.get("baseline_expected_recovered_paise", 0) / 100
            st.metric("Baseline Expected Recovery", f"₹{bl_exp:,.0f}",
                      help="Model-estimated recovery if ALL transactions used generic next-day retry")
        with c2:
            lz_exp = cf.get("lazarus_expected_recovered_paise", 0) / 100
            st.metric("LAZARUS Expected Recovery", f"₹{lz_exp:,.0f}",
                      help="Model-estimated recovery with archetype-specific actions")
        with c3:
            lift = cf.get("estimated_additional_recovered_paise", 0) / 100
            st.metric("Estimated Additional Lift", f"₹{lift:,.0f}",
                      delta=f"+{lift/bl_exp:.0%} relative improvement" if bl_exp > 0 else None)

        st.markdown("---")
        st.markdown("**Archetype-level counterfactual estimates**")
        rows = []
        for arch in ARCHETYPE_LIST:
            bl_r, lz_r = ARCHETYPE_RECOVERY_RATES.get(arch, (0, 0))
            rows.append({
                "Archetype": arch,
                "Baseline Action": "generic_retry_or_reminder",
                "LAZARUS Action": ARCHETYPES[arch]["recovery_action"],
                "Baseline Prob": f"{bl_r:.0%}",
                "LAZARUS Prob": f"{lz_r:.0%}",
                "Est. Lift": f"+{(lz_r - bl_r)*100:.0f}pp",
                "Note": "Safety block" if arch == "velocity_trap" else "",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Run `python -X utf8 batch_runner.py` to see counterfactual analysis.")

# ──────────────────────────────────────────────────────────
# TAB 4: Audit Trail
# ──────────────────────────────────────────────────────────
with tab4:
    st.markdown("### Immutable Audit Trail")
    st.markdown("Every decision is recorded in append-only SQLite. "
                "A DB-level trigger prevents any UPDATE or DELETE operation.")

    if has_audit:
        # Filters
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            arch_filter = st.multiselect("Filter by archetype", ARCHETYPE_LIST, default=[])
        with col_f2:
            verdict_filter = st.multiselect("Filter by gate verdict", ["ALLOW", "BLOCK", "DEFER"], default=[])
        with col_f3:
            outcome_filter = st.multiselect("Filter by outcome", ["SUCCESS", "FAILURE", "BLOCKED", "DEFERRED"], default=[])

        display_df = audit_df.copy()
        if arch_filter:
            display_df = display_df[display_df["archetype"].isin(arch_filter)]
        if verdict_filter:
            display_df = display_df[display_df["gate_verdict"].isin(verdict_filter)]
        if outcome_filter:
            display_df = display_df[display_df["outcome"].isin(outcome_filter)]

        cols_to_show = [
            "id", "txn_id", "archetype", "archetype_confidence",
            "failure_code", "prescribed_action",
            "gate_verdict", "gate_reason", "outcome",
            "customer_message", "strategist_reasoning",
            "recovered_amount_paise", "policy_version", "logged_at"
        ]
        existing_cols = [c for c in cols_to_show if c in display_df.columns]
        st.dataframe(display_df[existing_cols], use_container_width=True, height=480)
        st.markdown(f"Showing **{len(display_df)}** of **{len(audit_df)}** records")

        # ── Expandable forensic detail for any selected transaction
        st.markdown("---")
        sel_ids = display_df["id"].tolist()
        if sel_ids:
            sel_id = st.selectbox("Expand forensic report for audit ID:", sel_ids, key="audit_expand")
            row = display_df[display_df["id"] == sel_id].iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Archetype:** `{row.get('archetype','—')}`")
            c2.markdown(f"**Gate Verdict:** `{row.get('gate_verdict','—')}`")
            c3.markdown(f"**Outcome:** `{row.get('outcome','—')}`")
            msg = row.get("customer_message") or row.get("customer_message_hint")
            if msg and str(msg) not in ("None", "nan", ""):
                st.info(f"💬 **Customer message:** {msg}")
            reasoning = row.get("strategist_reasoning")
            if reasoning and str(reasoning) not in ("None", "nan", ""):
                st.markdown(f"**Strategist reasoning:** {reasoning}")
            st.caption(f"Gate reason: {row.get('gate_reason','—')}")

        st.markdown("---")
        st.markdown("**Audit integrity proof** — no UPDATE/DELETE possible")
        st.code("""
-- The guard trigger (embedded in SQLite schema):
CREATE TRIGGER prevent_audit_tampering
BEFORE UPDATE ON lazarus_audit
BEGIN
    SELECT RAISE(ABORT, 'LAZARUS: audit trail is append-only. UPDATE is forbidden.');
END;
        """, language="sql")
    else:
        st.info("Run `python -X utf8 batch_runner.py` to populate the audit trail.")

# ── Sandbox tab
with tab5:
    render_sandbox()

# ── Merchant Intelligence tab
with tab6:
    st.markdown("### 🏢 Merchant Risk Intelligence")
    st.markdown("Analyze failure archetypes and revenue at risk across the merchant portfolio. Actionable B2B insights.")
    if has_audit and "merchant_id" in audit_df.columns:
        import plotly.express as px
        
        st.markdown("#### Revenue at Risk by Merchant & Archetype")
        st.caption("Treemap of transaction volume (INR) failing at checkout, grouped by merchant and underlying cause.")
        df_tree = audit_df.groupby(["merchant_id", "archetype"])["amount_paise"].sum().reset_index()
        df_tree["amount_inr"] = df_tree["amount_paise"] / 100
        fig_tree = px.treemap(
            df_tree, path=[px.Constant("All Merchants"), "merchant_id", "archetype"], values="amount_inr",
            color="archetype",
            color_discrete_map=ARCH_COLORS,
            template="plotly_dark"
        )
        fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10), paper_bgcolor="rgba(0,0,0,0)")
        fig_tree.update_traces(marker=dict(cornerradius=5))
        st.plotly_chart(fig_tree, use_container_width=True)
        
        st.markdown("#### Merchant Action Briefs")
        merchants = []
        for m_id, group in audit_df.groupby("merchant_id"):
            total_fail = len(group)
            recovered = len(group[group["outcome"] == "SUCCESS"])
            top_arch = group["archetype"].mode()[0]
            
            # Simple heuristic recommendation based on domain model
            if top_arch == "velocity_trap":
                rec = "🔴 High fraud velocity. Increase 3D-secure stringency."
            elif top_arch == "empty_vault":
                rec = "🟡 Low liquidity. Enable Buy-Now-Pay-Later (BNPL) options."
            elif top_arch == "dropped_signal":
                rec = "🟢 High transient failures. Enable silent auto-retries."
            elif top_arch == "limit_breaker":
                rec = "🟡 High ticket limit drops. Route large baskets to Netbanking."
            else:
                rec = "Monitor archetype distribution."
                
            merchants.append({
                "Merchant ID": m_id,
                "Total Failures": total_fail,
                "LAZARUS Recovery": f"{recovered/total_fail:.0%}",
                "Top Failure Cause": top_arch,
                "Automated Recommendation": rec
            })
        st.dataframe(pd.DataFrame(merchants), hide_index=True, use_container_width=True)
    else:
        st.info("Run `python -X utf8 batch_runner.py` to generate merchant data.")

# ── Chat Simulator tab
with tab7:
    st.markdown("### 💬 The Negotiator (Interactive Chat)")
    st.markdown("Simulate a conversational recovery flow (e.g., overcoming price friction or liquidity issues).")
    
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": "Hi there! I noticed you had trouble completing your payment of ₹5000. Is there anything I can help you with?"}
        ]
        
    if "negotiator" not in st.session_state:
        from core.negotiator import NegotiatorAgent
        st.session_state.negotiator = NegotiatorAgent(context={"amount_inr": 5000, "archetype": "hesitant_hand"})

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if chat_prompt := st.chat_input("E.g., I don't get paid until Friday"):
        st.session_state.chat_messages.append({"role": "user", "content": chat_prompt})
        with st.chat_message("user"):
            st.markdown(chat_prompt)
            
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""
            for chunk in st.session_state.negotiator.send_message(chat_prompt):
                full_response += chunk
                # Live preview replacement while streaming
                display_text = full_response.replace("[LINK_GENERATED]", "[🔗 Click here to complete payment](https://rzp.io/i/demo)")
                response_placeholder.markdown(display_text + "▌")
            
            # Final clean replacement
            full_response = full_response.replace("[LINK_GENERATED]", "[🔗 Click here to complete payment](https://rzp.io/i/demo)")
            response_placeholder.markdown(full_response)
            
        st.session_state.chat_messages.append({"role": "assistant", "content": full_response})

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color: rgba(255,255,255,0.2); font-size:0.8rem;'>"
    "LAZARUS · Razorpay AI Buildathon 2026 · Track 03: AI Revenue Recovery · "
    "Policy version v1.0.0</div>",
    unsafe_allow_html=True
)
