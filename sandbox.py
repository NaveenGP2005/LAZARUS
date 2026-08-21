"""
LAZARUS — sandbox.py
Interactive Pipeline Sandbox — runs the full 4-layer pipeline live.
Strategist step uses Gemini streaming so reasoning types out in real time.
No audit trail entry is created during sandbox runs.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from config import ARCHETYPES, ARCHETYPE_LIST, COMPLIANCE_RULES
from core.strategist import GEMINI_SKIP_ARCHETYPES


# ─────────────────────────────────────────────────────────────────────────────
# Cached heavy components
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Loading Coroner…")
def _get_coroner():
    from core.coroner import Coroner
    return Coroner()


@st.cache_resource(show_spinner="Loading Strategist…")
def _get_strategist():
    from core.strategist import Strategist
    return Strategist()


# ─────────────────────────────────────────────────────────────────────────────
# Build synthetic transaction
# ─────────────────────────────────────────────────────────────────────────────

def _build_txn(error_code, amount_inr, method, risk_score, sim_hour):
    sim_time = datetime.now().replace(
        hour=sim_hour, minute=15, second=0, microsecond=0
    ).isoformat()
    return {
        "txn_id":          f"SANDBOX_{error_code}",
        "idx":             0,
        "amount_paise":    amount_inr * 100,
        "amount_inr":      amount_inr,
        "currency":        "INR",
        "payment_method":  method,
        "failure_code":    error_code,
        "failure_time":    sim_time,
        "merchant_id":     "MRC_SANDBOX",
        "buyer": {
            "customer_id":          "CUST_SANDBOX",
            "is_first_time_buyer":  False,
            "historical_txn_count": 5,
            "days_since_last_txn":  30,
            "prior_failures_7d":    1 if risk_score > 0.7 else 0,
        },
        "subscription_id": "sub_SANDBOX" if method == "emandate" else None,
        "risk_score":      risk_score,
        "retry_count":     0,
        "status":          "failed",
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTML card helpers
# ─────────────────────────────────────────────────────────────────────────────

def _step_card(number, title, colour, body_html):
    return f"""
<div style="background:linear-gradient(135deg,#0d1b2a,#1a1a2e);
            border:1px solid {colour}33;border-left:3px solid {colour};
            border-radius:10px;padding:1rem 1.2rem;margin-bottom:0.8rem;">
  <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.6rem;">
    <span style="background:{colour}22;color:{colour};border:1px solid {colour}44;
                 width:22px;height:22px;border-radius:50%;display:inline-flex;
                 align-items:center;justify-content:center;font-size:0.7rem;
                 font-weight:700;">{number}</span>
    <span style="color:{colour};font-weight:600;font-size:0.9rem;
                 text-transform:uppercase;letter-spacing:0.05em;">{title}</span>
  </div>
  {body_html}
</div>"""


def _kv(label, value, mono=False):
    font = "font-family:'JetBrains Mono',monospace;" if mono else ""
    return (
        f'<div style="margin:0.25rem 0;">'
        f'<span style="color:rgba(255,255,255,0.4);font-size:0.75rem;">{label}</span>'
        f'<br><span style="color:rgba(255,255,255,0.9);font-size:0.85rem;{font}">{value}</span>'
        f'</div>'
    )


def _verdict_badge(verdict):
    colours = {"ALLOW": ("#34d399","#052e16"), "BLOCK": ("#f87171","#1c0505"), "DEFER": ("#fbbf24","#1c1305")}
    fg, bg = colours.get(verdict, ("#94a3b8","#0f172a"))
    return (f'<span style="background:{bg};color:{fg};border:1px solid {fg}33;'
            f'padding:0.15rem 0.7rem;border-radius:100px;font-size:0.8rem;'
            f'font-weight:700;letter-spacing:0.05em;">{verdict}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Card renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_coroner_card(coroner_result):
    archetype  = coroner_result["archetype"]
    conf_pct   = f"{coroner_result['confidence']:.0%}"
    method_tag = "Rule Engine" if coroner_result["method"] == "rule_engine" else "Bayesian Network"
    factors    = " · ".join(coroner_result.get("causal_factors", []))
    scores_top = sorted(coroner_result["all_scores"].items(), key=lambda x: -x[1])[:3]
    scores_html = " &nbsp;".join(
        f'<span style="color:rgba(255,255,255,0.5)">{a}:{v:.0%}</span>'
        for a, v in scores_top
    )
    body = (
        _kv("Archetype", f"<strong style='color:#a78bfa'>{archetype.replace('_',' ').title()}</strong>  ({conf_pct})")
        + _kv("Classification method", method_tag)
        + _kv("Causal factors", factors or "—", mono=True)
        + _kv("Probability distribution (top 3)", scores_html)
    )
    st.markdown(_step_card(1, "CORONER", "#a78bfa", body), unsafe_allow_html=True)


def _render_strategist_card(playbook):
    action   = playbook.get("chosen_action", "—")
    reasoning= playbook.get("reasoning", "—")
    msg      = playbook.get("customer_message_hint") or \
               "<em style='color:rgba(255,255,255,0.35)'>No customer contact for this archetype</em>"
    risk     = playbook.get("risk", "—")
    source   = playbook.get("source", "fallback")
    src_badge = ('<span style="color:#34d399;font-size:0.75rem">⚡ Gemini</span>'
                 if "gemini" in source
                 else '<span style="color:#94a3b8;font-size:0.75rem">📋 Expert playbook</span>')
    body = (
        _kv("Chosen action", f"<code style='color:#63c8ff'>{action}</code>")
        + _kv("Reasoning", f"<em>{reasoning}</em>")
        + _kv("Customer message template", f'<span style="color:#fbbf24">{msg}</span>')
        + _kv("Risk rating", risk)
        + f'<div style="margin-top:0.4rem">{src_badge}</div>'
    )
    st.markdown(_step_card(2, "STRATEGIST", "#63c8ff", body), unsafe_allow_html=True)


def _render_gate_card(gate):
    verdict = gate["verdict"]
    reason  = gate["reason"]
    defer_ts= gate.get("defer_until")
    v_colors= {"ALLOW": "#34d399", "BLOCK": "#f87171", "DEFER": "#fbbf24"}
    color   = v_colors.get(verdict, "#94a3b8")
    body = (
        f'<div style="margin-bottom:0.5rem">{_verdict_badge(verdict)}</div>'
        + _kv("Reason", reason, mono=True)
        + (_kv("Defer until", defer_ts) if defer_ts else "")
    )
    st.markdown(_step_card(3, "COMPLIANCE GATE", color, body), unsafe_allow_html=True)


def _render_executor_card(gate, txn, playbook):
    verdict = gate["verdict"]
    v_colors= {"ALLOW": "#34d399", "BLOCK": "#f87171", "DEFER": "#fbbf24"}
    color   = v_colors.get(verdict, "#94a3b8")
    archetype = txn.get("failure_code", "")

    if verdict == "ALLOW":
        title = "EXECUTOR — Action Approved"
        cfg   = ARCHETYPES.get(txn.get("_archetype",""), {})
        defer_days  = cfg.get("defer_days", 0)
        defer_hours = cfg.get("defer_hours", 0)
        defer_mins  = cfg.get("defer_minutes", 0)
        if defer_days or defer_hours or defer_mins:
            exec_at = (datetime.now() + timedelta(
                days=defer_days, hours=defer_hours, minutes=defer_mins
            )).strftime("%Y-%m-%d %H:%M")
            timing = f"Execute at {exec_at}"
        else:
            timing = "Execute immediately"
        payload = json.dumps({
            "amount": txn["amount_paise"], "currency": "INR",
            "description": f"LAZARUS Recovery — {txn.get('failure_code')}",
            "notes": {
                "action": playbook.get("chosen_action"),
                "policy_version": "v1.0.0",
                "original_txn_id": txn["txn_id"],
                "failure_code": txn["failure_code"],
            },
        }, indent=2)
        body = (
            _kv("Timing", timing)
            + _kv("Razorpay payload preview", "")
            + f'<pre style="background:#0a0e1a;color:#63c8ff;padding:0.6rem;'
              f'border-radius:6px;font-size:0.72rem;overflow-x:auto;margin-top:0.3rem">{payload}</pre>'
            + '<div style="color:rgba(255,255,255,0.3);font-size:0.75rem;margin-top:0.4rem">'
              '⚠ Sandbox mode — no real API call made</div>'
        )
    elif verdict == "BLOCK":
        title = "EXECUTOR — Action Blocked"
        body  = _kv("Result", "<strong style='color:#f87171'>No Razorpay call made.</strong> Compliance Gate blocked execution.")
    else:
        title = "EXECUTOR — Action Deferred"
        body  = _kv("Result", f"<strong style='color:#fbbf24'>Scheduled for {gate.get('defer_until','later')}.</strong> No contact now.")

    st.markdown(_step_card(4, title, color, body), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main render — called from dashboard.py
# ─────────────────────────────────────────────────────────────────────────────

def render_sandbox():
    st.markdown("### 🎮 Live Pipeline Sandbox")
    st.markdown(
        "Build a synthetic failed payment and watch all four LAZARUS layers execute. "
        "Gemini reasoning streams **token-by-token** in real time. "
        "**No audit record is created.**"
    )

    if "sandbox_result" not in st.session_state:
        st.session_state.sandbox_result = None

    # ── Error code list
    code_options = []
    for arch, cfg in ARCHETYPES.items():
        for code in cfg["error_codes"]:
            code_options.append((code, arch))

    col_in, col_out = st.columns([1, 1.3], gap="large")

    with col_in:
        st.markdown("#### Configure Transaction")
        selected = st.selectbox(
            "NPCI / Gateway Failure Code",
            [f"{c}  [{a}]" for c, a in code_options],
        )
        error_code = selected.split("  [")[0].strip()
        amount_inr = st.slider("Amount (₹)", 100, 100_000, 5_000, step=100)
        method     = st.selectbox("Payment Method", ["upi", "card", "netbanking", "emandate", "wallet"])
        risk_score = st.slider("Risk Score", 0.0, 1.0, 0.05, step=0.05,
                               help="0 = clean · 1.0 = max fraud signal")
        sim_hour   = st.slider("Simulated Hour (24h)", 0, 23, 14,
                               help="Try 23 for Quiet Hours enforcement")
        is_quiet   = sim_hour >= COMPLIANCE_RULES["quiet_hours_start"] or \
                     sim_hour < COMPLIANCE_RULES["quiet_hours_end"]
        st.caption(f"{sim_hour:02d}:00 — {'🔴 Quiet hours active' if is_quiet else '🟢 Business hours'}")
        st.markdown("---")
        run = st.button("🔬 Run LAZARUS Analysis", type="primary", use_container_width=True)

    with col_out:
        if run:
            st.session_state.sandbox_result = None  # reset
            txn = _build_txn(error_code, amount_inr, method, risk_score, sim_hour)

            coroner   = _get_coroner()
            strategist= _get_strategist()

            # ── Step 1: Coroner (instant)
            coroner_result = coroner.classify(txn)
            archetype = coroner_result["archetype"]
            txn["_archetype"] = archetype          # store for executor card
            _render_coroner_card(coroner_result)

            # ── Step 2: Strategist — streaming or instant
            needs_stream = bool(strategist.model) and archetype not in GEMINI_SKIP_ARCHETYPES
            strat_ph = st.empty()

            if needs_stream:
                # Show live streaming in placeholder
                streamed = ""
                playbook = None
                strat_ph.markdown(
                    _step_card(2, "STRATEGIST  ⚡ Gemini streaming…", "#63c8ff",
                               '<span style="color:rgba(255,255,255,0.3)">Waiting for tokens…</span>'),
                    unsafe_allow_html=True,
                )
                for chunk, final_playbook in strategist.generate_playbook_stream(txn, coroner_result):
                    if final_playbook is not None:
                        playbook = final_playbook
                    else:
                        streamed += chunk
                        strat_ph.markdown(
                            _step_card(2, "STRATEGIST  ⚡ Gemini streaming…", "#63c8ff",
                                       f'<pre style="color:#63c8ff;font-size:0.78rem;'
                                       f'white-space:pre-wrap;background:transparent;'
                                       f'margin:0;padding:0">{streamed}▊</pre>'),
                            unsafe_allow_html=True,
                        )
                strat_ph.empty()
            else:
                playbook = strategist.generate_playbook(txn, coroner_result)

            _render_strategist_card(playbook)

            # ── Step 3: Compliance Gate
            from core.compliance import ComplianceGate
            sim_now = datetime.now().replace(hour=sim_hour, minute=0, second=0, microsecond=0)
            gate_obj = ComplianceGate()
            gate_decision = gate_obj.evaluate(
                transaction=txn, archetype=archetype,
                proposed_action=playbook.get("chosen_action", "manual_review"),
                _now=sim_now,
            )
            _render_gate_card(gate_decision.to_dict())

            # ── Step 4: Executor preview
            _render_executor_card(gate_decision.to_dict(), txn, playbook)

            # Store for re-render on page refresh
            st.session_state.sandbox_result = {
                "txn": txn, "coroner": coroner_result,
                "playbook": playbook, "gate": gate_decision.to_dict(),
            }

        elif st.session_state.sandbox_result:
            # Re-render stored result without re-running pipeline
            r = st.session_state.sandbox_result
            _render_coroner_card(r["coroner"])
            _render_strategist_card(r["playbook"])
            _render_gate_card(r["gate"])
            _render_executor_card(r["gate"], r["txn"], r["playbook"])
        else:
            st.markdown(
                "<div style='color:rgba(255,255,255,0.3);text-align:center;"
                "padding:3rem 0'>Configure a transaction and click Run.</div>",
                unsafe_allow_html=True,
            )
