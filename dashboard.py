import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import os

st.set_page_config(
    page_title="Human Digital Twin Tutor Dashboard", 
    page_icon="🎓", 
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "interactions.db"

STRATEGY_MAP = {
    1: "1: ONBOARDING",
    2: "2: STANDARD_ROLEPLAY",
    3: "3: SCAFFOLD_HINT",
    4: "4: CORRECT_AND_REACT",
    5: "5: INCREASE_DIFFICULTY"
}

def init_db():
    """Ensure table structure includes session_id and phase columns."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interaction_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            phase TEXT,
            user_text TEXT,
            response_latency REAL,
            uncertainty_detected INTEGER,
            knowledge REAL,
            engagement REAL,
            support_need REAL,
            confidence_expression REAL,
            strategy_id INTEGER,
            strategy_reason TEXT,
            tutor_reply TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_data():
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM interaction_logs ORDER BY timestamp ASC", conn)
        conn.close()
        
        if df.empty:
            return df

        # Smart Auto-Scaling: Convert 0.0-1.0 float ranges to 0-100 scale for clean dashboard display
        metric_cols = ['knowledge', 'engagement', 'support_need', 'confidence_expression']
        for col in metric_cols:
            if col in df.columns and not df[col].dropna().empty:
                if df[col].max() <= 1.0:
                    df[col] = df[col] * 100.0

        return df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
st.sidebar.title("⚙️ Session Controls")

df_raw = load_data()

# Session Filtering
selected_session = "All Sessions"
if not df_raw.empty and "session_id" in df_raw.columns:
    sessions = ["All Sessions"] + [s for s in df_raw["session_id"].dropna().unique() if s]
    selected_session = st.sidebar.selectbox("Filter by Participant Session:", sessions)

# Filter Dataframe
if selected_session != "All Sessions" and not df_raw.empty:
    df = df_raw[df_raw["session_id"] == selected_session].copy()
else:
    df = df_raw.copy()

st.sidebar.markdown("---")

# Data Export for SPSS / R
if not df.empty:
    csv = df.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button(
        label="📥 Export Logs to CSV (for SPSS/R)",
        data=csv,
        file_name="hdt_interaction_logs.csv",
        mime="text/csv",
    )

st.sidebar.markdown("---")

# Wipe DB Button
if st.sidebar.button("🗑️ Clear All Session History (Wipe DB)", type="primary"):
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    init_db()
    st.sidebar.success("Database wiped! Starting fresh.")
    st.rerun()

# ==========================================
# MAIN DASHBOARD CONTENT
# ==========================================
st.title("🎓 Master's Dissertation: Human Digital Twin Dashboard")
st.markdown("Real-time monitoring and historical trajectory analysis of learner state, latency, and pedagogical strategy selection.")

if st.button("🔄 Refresh Data"):
    st.rerun()

if df.empty:
    st.warning("⚠️ No interaction logs found in `interactions.db`. Run a session in Unity to populate data!")
else:
    # --------------------------------------
    # 1. KEY SUMMARY METRICS
    # --------------------------------------
    col1, col2, col3, col4, col5 = st.columns(5)
    
    total_turns = len(df)
    avg_latency = df['response_latency'].mean() if 'response_latency' in df.columns else 0
    avg_knowledge = df['knowledge'].mean() if 'knowledge' in df.columns else 0
    avg_confidence = df['confidence_expression'].mean() if 'confidence_expression' in df.columns else 0
    
    col1.metric("Total Turns", total_turns)
    col2.metric("Avg Latency", f"{avg_latency:.2f}s")
    col3.metric("Avg Knowledge", f"{avg_knowledge:.1f}%")
    col4.metric("Avg Confidence", f"{avg_confidence:.1f}%")
    
    if 'strategy_id' in df.columns and not df['strategy_id'].dropna().empty:
        most_common_strat = int(df['strategy_id'].mode()[0])
        strat_label = STRATEGY_MAP.get(most_common_strat, f"Strategy {most_common_strat}")
    else:
        strat_label = "N/A"
        
    col5.metric("Top Strategy Used", strat_label)

    st.markdown("---")

    # --------------------------------------
    # 2. TABS FOR DETAILED ANALYSIS
    # --------------------------------------
    tab_analytics, tab_transcript, tab_raw_data = st.tabs(["📈 Trajectory Analytics", "💬 Dialogue Transcript", "📋 Raw Data Table"])

    # --------------------------------------
    # TAB 1: ANALYTICS & CHARTS
    # --------------------------------------
    with tab_analytics:
        # Trajectory Line Chart
        st.subheader("📈 Digital Twin State Trajectory")
        chart_cols = [c for c in ['knowledge', 'engagement', 'support_need', 'confidence_expression'] if c in df.columns]
        
        if chart_cols:
            chart_df = df[['timestamp'] + chart_cols].copy()
            chart_df['Turn'] = range(1, len(chart_df) + 1)
            
            fig_line = px.line(
                chart_df, 
                x='Turn', 
                y=chart_cols,
                labels={'value': 'Scale (0 - 100%)', 'variable': 'Digital Twin Metric'},
                title="Evolution of Learner State Across Conversation Turns",
                markers=True
            )
            fig_line.update_layout(yaxis=dict(range=[0, 105]), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_line, use_container_width=True)

        st.markdown("---")

        # Strategy & Uncertainty Distributions
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("🎯 Pedagogical Strategy Distribution")
            if 'strategy_id' in df.columns and not df['strategy_id'].dropna().empty:
                strat_counts = df['strategy_id'].value_counts().reset_index()
                strat_counts.columns = ['Strategy_ID', 'Count']
                strat_counts['Strategy Name'] = strat_counts['Strategy_ID'].map(lambda x: STRATEGY_MAP.get(int(x), f"Strategy {x}"))
                
                fig_strat = px.bar(
                    strat_counts, 
                    x='Strategy Name', 
                    y='Count', 
                    color='Strategy Name',
                    title="Frequency of Strategies Selected by Backend"
                )
                st.plotly_chart(fig_strat, use_container_width=True)

        with col_b:
            st.subheader("❓ Uncertainty & Hesitation Detections")
            if 'uncertainty_detected' in df.columns and not df['uncertainty_detected'].dropna().empty:
                unc_counts = df['uncertainty_detected'].value_counts().reset_index()
                unc_counts.columns = ['Uncertainty', 'Count']
                unc_counts['Uncertainty'] = unc_counts['Uncertainty'].map({0: 'Clear Response', 1: 'Hesitant / Uncertain'})
                fig_unc = px.pie(unc_counts, names='Uncertainty', values='Count', hole=0.4, title="Hesitation Ratio")
                st.plotly_chart(fig_unc, use_container_width=True)

        # Latency Bar Chart
        st.subheader("⏱️ Response Latency per Turn")
        if 'response_latency' in df.columns:
            df_lat = df.copy()
            df_lat['Turn'] = range(1, len(df_lat) + 1)
            fig_lat = px.bar(
                df_lat, 
                x='Turn', 
                y='response_latency', 
                labels={'Turn': 'Turn Number', 'response_latency': 'Latency (seconds)'},
                title="Learner Reaction Speed per Interaction Turn"
            )
            st.plotly_chart(fig_lat, use_container_width=True)

    # --------------------------------------
    # TAB 2: DIALOGUE TRANSCRIPT
    # --------------------------------------
    with tab_transcript:
        st.subheader("💬 Conversation History")
        
        for idx, row in df.iterrows():
            turn_num = idx + 1
            user_msg = row.get('user_text', '')
            tutor_msg = row.get('tutor_reply', '')
            latency = row.get('response_latency', 0)
            strat = STRATEGY_MAP.get(int(row.get('strategy_id', 2)), 'Standard')
            reason = row.get('strategy_reason', 'N/A')
            know = row.get('knowledge', 0)
            
            with st.expander(f"Turn {turn_num} | Strategy: {strat} | Latency: {latency:.2f}s", expanded=False):
                st.markdown(f"**Learner State:** Knowledge: `{know:.1f}%` | Strategy Reason: *\"{reason}\"*")
                
                if user_msg:
                    with st.chat_message("user"):
                        st.write(user_msg)
                        
                if tutor_msg:
                    with st.chat_message("assistant"):
                        st.write(tutor_msg)

    # --------------------------------------
    # TAB 3: RAW DATA TABLE
    # --------------------------------------
    with tab_raw_data:
        st.subheader("📋 Complete Interaction Log Table")
        
        display_df = df.copy()
        if 'strategy_id' in display_df.columns:
            display_df['strategy_name'] = display_df['strategy_id'].map(lambda x: STRATEGY_MAP.get(int(x), str(x)))
        
        st.dataframe(display_df, use_container_width=True)