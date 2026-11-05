"""Streamlit dashboard. All incident and memory operations go through FastAPI."""

import streamlit as st

from frontend.api_client import ApiError, IncidentMindApi

st.set_page_config(page_title="IncidentMind AI", page_icon="🛠️", layout="wide")
st.title("IncidentMind AI")
st.caption("Incident response recommendations grounded in engineer-verified history. Recovery actions are never executed by this dashboard.")

api = IncidentMindApi()


def show_error(error: Exception) -> None:
    st.error(str(error))
    st.caption("Check that the FastAPI service is running and INCIDENTMIND_API_URL points to it.")


def render_feed_and_detail() -> None:
    st.header("Incident feed")
    try:
        rows = api.list_incidents()
    except ApiError as error:
        show_error(error)
        return
    if not rows:
        st.info("No incidents have been recorded yet. Ingest an alert through the API to begin.")
        return

    feed = []
    for row in rows:
        incident = row["incident"]
        feed.append({
            "ID": incident["id"],
            "Service": incident["service"],
            "Severity": incident["severity"],
            "Category": incident.get("category") or "Unknown",
            "Status": row["feedback_outcome"] or "open",
            "Created": incident["created_at"],
        })
    real_feed = [row for row in feed if not next(item["synthetic"] for item in rows if item["incident"]["id"] == row["ID"])]
    synthetic_feed = [row for row in feed if next(item["synthetic"] for item in rows if item["incident"]["id"] == row["ID"])]
    if real_feed:
        st.subheader("Real incidents")
        st.dataframe(real_feed, use_container_width=True, hide_index=True)
    if synthetic_feed:
        st.subheader("Synthetic Chaos Dojo scenarios")
        st.caption("These generated examples are displayed separately and excluded from verified outcome statistics.")
        st.dataframe(synthetic_feed, use_container_width=True, hide_index=True)

    selected = st.selectbox("Incident details", [row["ID"] for row in feed], format_func=lambda value: next(
        f"{row['Service']} · {row['Severity']} · {row['ID']}" for row in feed if row["ID"] == value
    ))
    try:
        incident = api.get_incident(selected)
    except ApiError as error:
        show_error(error)
        return
    st.subheader(f"{incident['service']} · {incident.get('category') or 'Unclassified'}")
    st.write(incident["error"])
    analysis_key = f"analysis:{selected}"
    if st.button("Analyze with recalled memory", key=f"analyze:{selected}"):
        try:
            st.session_state[analysis_key] = api.analyze(selected, innovation_enabled=True)
        except ApiError as error:
            show_error(error)
    analysis = st.session_state.get(analysis_key)
    if analysis:
        if analysis["analysis"]["hypotheses"]:
            st.markdown("**Suspected causes**")
            for hypothesis in analysis["analysis"]["hypotheses"]:
                st.write(f"Suspected: {hypothesis['cause']}")
                st.caption(hypothesis["reasoning"])
        else:
            st.info(analysis["message"])
        st.markdown("**Recommended steps · engineer review required**")
        for step in analysis["analysis"]["recommended_steps"]:
            st.write(f"• {step}")
        if analysis["warnings"]:
            st.warning("\n\n".join(analysis["warnings"]))
        for warning in analysis.get("anti_runbook_warnings", []):
            st.warning(warning["message"])
            for context in warning["context"]:
                st.caption(context)
        st.markdown("**Memory evidence recalled by Hindsight**")
        if not analysis["evidence"]:
            st.info("No relevant historical evidence was recalled.")
        for evidence in analysis["evidence"]:
            title = evidence.get("incident_id") or "Historical evidence"
            with st.expander(f"{title} · relevance {evidence.get('relevance') if evidence.get('relevance') is not None else 'not provided'}"):
                st.write(evidence.get("source_text") or evidence["raw_text"])
                st.caption("Historical evidence from memory; current cause hypotheses remain suspected until an engineer verifies them.")

    st.subheader("Engineer feedback")
    with st.form(f"feedback:{selected}"):
        verified_cause = st.text_input("Verified cause")
        steps_text = st.text_area("Steps taken (one per line)")
        outcome = st.selectbox("Outcome", ["resolved", "failed", "partial"])
        notes = st.text_area("Engineer notes")
        submitted = st.form_submit_button("Save feedback")
    if submitted:
        if not verified_cause.strip():
            st.error("Enter the engineer-verified cause before saving.")
        else:
            payload = {
                "verified_cause": verified_cause,
                "steps_taken": [line.strip() for line in steps_text.splitlines() if line.strip()],
                "outcome": outcome,
                "notes": notes,
            }
            try:
                result = api.submit_feedback(selected, payload)
                st.success(f"Feedback recorded. Hindsight retained: {result['memory_retained']}.")
                if result.get("warning"):
                    st.warning(result["warning"])
            except ApiError as error:
                show_error(error)


def render_replay() -> None:
    st.header("Replay Lab")
    st.caption("Compare the same ordered incidents with memory disabled and enabled. Metrics are computed from stored outcomes; no improvement score is invented.")
    try:
        rows = api.list_incidents(limit=200)
    except ApiError as error:
        show_error(error)
        return
    labeled = [row for row in rows if row.get("feedback_outcome")]
    if not labeled:
        st.info("Record engineer feedback on incidents before replaying verified outcomes.")
        return
    id_to_label = {
        row["incident"]["id"]: f"{row['incident']['service']} · {row['feedback_outcome']} · {row['incident']['id']}"
        for row in labeled
    }
    choices = st.multiselect("Ordered incident sequence", list(id_to_label), format_func=lambda item: id_to_label[item], key="replay_ids")
    if st.button("Run memory comparison", disabled=len(choices) < 1):
        try:
            st.session_state["replay_result"] = api.replay(choices)
        except ApiError as error:
            show_error(error)
    result = st.session_state.get("replay_result")
    if result:
        st.caption(f"Run {result['run_id']} · isolated Hindsight bank {result.get('memory_bank_id') or 'not reported'}")
        disabled = result["memory_disabled"]["steps"]
        enabled = result["memory_enabled"]["steps"]
        left, right = st.columns(2)
        for column, label, steps in ((left, "Memory disabled", disabled), (right, "Memory enabled", enabled)):
            with column:
                st.subheader(label)
                for step in steps:
                    st.write(f"{step['step']}. {step['incident_id']}")
                    st.caption(
                        f"Correct prior cause cited: {step['correct_prior_cause_cited']}; "
                        f"steps to verified fix: {step['steps_to_verified_fix']}; "
                        f"matched cause: {step['matched_verified_cause'] or 'none'}"
                    )
        chart_rows = []
        for label, steps in (("Memory disabled", disabled), ("Memory enabled", enabled)):
            for step in steps:
                chart_rows.append({
                    "Incident step": step["step"],
                    "Mode": label,
                    "Steps to verified fix": step["steps_to_verified_fix"],
                })
        if any(row["Steps to verified fix"] is not None for row in chart_rows):
            import pandas as pd

            chart = pd.DataFrame(chart_rows).pivot(index="Incident step", columns="Mode", values="Steps to verified fix")
            st.line_chart(chart)
        st.json(result)


def render_learning() -> None:
    st.header("Learning and memory")
    try:
        memory = api.memory_stats()
        origins = api.memory_origin_stats()
        outcomes = api.outcome_stats()
    except ApiError as error:
        show_error(error)
        return
    first, second, third, fourth = st.columns(4)
    first.metric("Engineer feedback records", memory["feedback_records"])
    second.metric("Real incidents retained", origins["real_retained_in_hindsight"])
    third.metric("Synthetic examples retained", origins["synthetic_retained_in_hindsight"])
    fourth.metric("Total confirmed retains", memory["retained_in_hindsight"])
    st.caption("Counts come from local feedback records and confirmed Retain responses; this is not a live Hindsight bank inventory.")
    st.subheader("Recorded outcomes")
    st.json(outcomes)


feed_tab, replay_tab, learning_tab = st.tabs(["Incident feed & detail", "Replay Lab", "Learning & memory"])
with feed_tab:
    render_feed_and_detail()
with replay_tab:
    render_replay()
with learning_tab:
    render_learning()
