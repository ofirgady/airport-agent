import os
import uuid

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

SUGGESTIONS = {
    ":material/query_stats: JFK traffic": "What is the current traffic at JFK?",
    ":material/compare_arrows: Compare JFK and LAX": "Compare JFK and LAX for investment potential",
    ":material/trending_up: New England growth": "Which airports in New England have the strongest growth?",
}

st.set_page_config(
    page_title="Airport Investment Agent",
    page_icon="✈️",
    layout="centered",
)

st.markdown(
    """
    <style>
    [data-testid="stSidebarUserContent"],
    [data-testid="stSidebarUserContent"] > div,
    .eelgd2m4 {
        padding-top: 0.5rem !important;
        gap: 0.5rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

try:
    all_runs = requests.get(f"{API_URL}/runs", timeout=10).json()
except requests.RequestException:
    all_runs = []


def transcript_for(session_id: str) -> list[dict]:
    messages = []
    for run in all_runs:
        if run["session_id"] != session_id:
            continue
        messages.append({"role": "user", "content": run["query"]})
        messages.append({"role": "assistant", "content": run["response"]})
    return messages


with st.sidebar:
    st.header("Conversations", text_alignment="center")
    if st.button("New chat", width="stretch", type="primary", icon=":material/add:"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []

    sessions: dict[str, dict] = {}
    for run in all_runs:  # runs.jsonl is append-only -> already chronological
        sid = run["session_id"]
        if sid not in sessions:
            sessions[sid] = {"preview": run["query"]}
        sessions[sid]["last_timestamp"] = run["timestamp"]

    ordered_session_ids = sorted(
        sessions, key=lambda sid: sessions[sid]["last_timestamp"], reverse=True
    )

    for sid in ordered_session_ids:
        preview = sessions[sid]["preview"]
        if len(preview) > 28:
            preview = preview[:28].rstrip() + "…"
        is_active = sid == st.session_state.session_id
        if st.button(
            preview,
            key=f"session-{sid}",
            width="stretch",
            type="primary" if is_active else "secondary",
        ):
            st.session_state.session_id = sid
            st.session_state.messages = transcript_for(sid)

st.title("Airport Investment Agent", text_alignment="center")
st.space("large")

for message in st.session_state.messages:
    avatar = ":material/flight:" if message["role"] == "assistant" else None
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
    st.space("medium")

prompt = st.chat_input("Ask about airport traffic, capacity, or investment potential...")

if "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

if not st.session_state.messages and not prompt:
    with st.container(horizontal_alignment="center"):
        selected = st.pills(
            "Try asking:",
            list(SUGGESTIONS.keys()),
            label_visibility="collapsed",
        )
    if selected:
        st.session_state.pending_prompt = SUGGESTIONS[selected]
        st.rerun()

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    st.space("medium")

    with st.chat_message("assistant", avatar=":material/flight:"):
        skeleton = st.skeleton()

        def stream_chunks():
            # SSE messages are "event: <type>\ndata: <payload>\n\n" -- track
            # the most recent event type so a backend-side event: error
            # (api.py's chat_stream, when the agent run itself fails
            # mid-stream) surfaces as a real error here instead of being
            # displayed as if it were ordinary streamed answer text.
            event_type = "message"
            first_chunk = True
            with requests.post(
                f"{API_URL}/chat",
                json={"session_id": st.session_state.session_id, "message": prompt},
                stream=True,
                timeout=60,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if line == "":
                        event_type = "message"
                        continue
                    if line.startswith("event: "):
                        event_type = line.removeprefix("event: ")
                        continue
                    if line.startswith("data: "):
                        data = line.removeprefix("data: ")
                        if event_type == "error":
                            raise RuntimeError(data)
                        if first_chunk:
                            skeleton.empty()
                            first_chunk = False
                        yield data

        try:
            answer = st.write_stream(stream_chunks)
        except (requests.RequestException, RuntimeError) as error:
            skeleton.empty()
            answer = f"Error reaching the agent API: {error}"
            st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
