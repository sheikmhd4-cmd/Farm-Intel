import os
import io
import json
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from dotenv import load_dotenv
from supabase import create_client
from huggingface_hub import InferenceClient

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

# ---------------- LOAD ENV ----------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
ADMIN_PASSKEY = os.getenv("ADMIN_PASSKEY")
AI_MODEL = os.getenv("AI_MODEL")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
hf_client = InferenceClient(token=HF_TOKEN)

# ---------------- PAGE CONFIG ----------------

st.set_page_config(page_title="AgriSense AI", layout="wide")

# ---------------- SESSION ----------------

for k in [
    "auth",
    "role",
    "email",
    "results",
]:
    if k not in st.session_state:
        st.session_state[k] = None

# ---------------- AI ENGINE ----------------

SYSTEM_PROMPT = """
You are an Indian agriculture and crop market expert.

Given a crop name, analyze and return STRICT JSON:

{
 "sowing_season": "",
 "harvest_time": "",
 "estimated_cost_per_acre": "",
 "transport_cost_estimate": "",
 "best_selling_price_range": "",
 "profitability_comment": ""
}

Keep language simple.
All prices in INR.
"""

def analyze_crop_ai(crop: str):
    prompt = SYSTEM_PROMPT + f"\nCrop: {crop}\nJSON:"

    res = hf_client.text_generation(
        model=AI_MODEL,
        prompt=prompt,
        max_new_tokens=350,
        temperature=0.3,
    )

    start = res.find("{")
    end = res.rfind("}") + 1

    parsed = json.loads(res[start:end])
    return parsed

# ---------------- AUTH UI ----------------

if not st.session_state.auth:

    col1, col2, col3 = st.columns([1, 1.6, 1])

    with col2:

        st.markdown("<h1 style='text-align:center;'>🌱 AgriSense AI</h1>", unsafe_allow_html=True)

        login_tab, reg_tab = st.tabs(["Login", "Register"])

        # -------- LOGIN --------

        with login_tab:

            with st.form("login_form"):

                email = st.text_input("Email")
                password = st.text_input("Password", type="password")

                role_choice = st.selectbox(
                    "Login as",
                    ["User", "Admin"],
                )

                admin_key = None
                if role_choice == "Admin":
                    admin_key = st.text_input("Admin Passkey", type="password")

                submitted = st.form_submit_button("Login", use_container_width=True)

                if submitted:

                    try:
                        res = supabase.auth.sign_in_with_password(
                            {"email": email, "password": password}
                        )

                        if res and res.session:

                            if role_choice == "Admin" and admin_key != ADMIN_PASSKEY:
                                st.error("Invalid Admin Passkey.")
                            else:
                                st.session_state.auth = True
                                st.session_state.role = role_choice
                                st.session_state.email = email

                                supabase.table("login_logs").insert(
                                    {
                                        "email": email,
                                        "role": role_choice,
                                        "time": datetime.now().isoformat(),
                                    }
                                ).execute()

                                st.rerun()

                        else:
                            st.error("Login failed.")

                    except Exception as e:
                        st.error("Authentication error.")

        # -------- REGISTER --------

        with reg_tab:

            with st.form("reg_form"):

                r_email = st.text_input("Email", key="r1")
                r_pass = st.text_input("Password", type="password", key="r2")

                if st.form_submit_button("Create Account"):

                    try:
                        supabase.auth.sign_up(
                            {"email": r_email, "password": r_pass}
                        )
                        st.success("Account created.")
                    except Exception as e:
                        st.error(str(e))

# ---------------- MAIN APP ----------------

else:

    # ---------- SIDEBAR ----------

    st.sidebar.markdown(
        f"""
        ### 🌱 AgriSense AI  
        **{st.session_state.role}**  
        {st.session_state.email}
        """
    )

    nav = ["Crop Analysis"]

    if st.session_state.role == "Admin":
        nav.extend(["User Logs", "Research History"])

    page = st.sidebar.radio("Navigation", nav)

    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()

    # ---------------- CROP ANALYSIS ----------------

    if page == "Crop Analysis":

        st.header("🌾 Crop Intelligence Engine")

        crop = st.text_input("Enter Crop Name (e.g., Tomato, Onion, Cotton)")

        if st.button("Analyze Crop", use_container_width=True) and crop:

            with st.spinner("Analyzing market + farming cycle..."):

                try:
                    result = analyze_crop_ai(crop)

                    st.session_state.results = result

                    supabase.table("crop_history").insert(
                        {
                            "email": st.session_state.email,
                            "role": st.session_state.role,
                            "crop": crop,
                            "result": json.dumps(result),
                            "time": datetime.now().isoformat(),
                        }
                    ).execute()

                except Exception as e:
                    st.error("AI failed. Check token or model.")

        if st.session_state.results:

            r = st.session_state.results

            c1, c2 = st.columns([1.2, 1])

            with c1:

                st.subheader("📊 Analysis Summary")

                for k, v in r.items():
                    st.info(f"**{k.replace('_',' ').title()}**: {v}")

            with c2:

                fig = go.Figure(
                    go.Bar(
                        x=[40, 30, 30],
                        y=["Production Cost", "Transport", "Profit Margin"],
                        orientation="h",
                    )
                )

                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

            # ---------- PDF ----------

            pdf_buffer = io.BytesIO()
            styles = getSampleStyleSheet()

            doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)

            elements = [
                Paragraph("AgriSense AI — Crop Report", styles["Title"]),
                Spacer(1, 20),
            ]

            for k, v in r.items():
                elements.append(
                    Paragraph(f"<b>{k.replace('_',' ').title()}</b>: {v}", styles["Normal"])
                )
                elements.append(Spacer(1, 10))

            doc.build(elements)

            st.download_button(
                "📥 Download PDF Report",
                pdf_buffer.getvalue(),
                file_name=f"{crop}_analysis.pdf",
                use_container_width=True,
            )

    # ---------------- ADMIN: USER LOGS ----------------

    elif page == "User Logs":

        st.header("🔐 Login History")

        data = supabase.table("login_logs").select("*").order("time", desc=True).execute()

        if data.data:
            st.dataframe(pd.DataFrame(data.data), use_container_width=True)
        else:
            st.warning("No logs.")

    # ---------------- ADMIN: RESEARCH HISTORY ----------------

    elif page == "Research History":

        st.header("📚 Crop Queries")

        data = supabase.table("crop_history").select("*").order("time", desc=True).execute()

        if data.data:
            st.dataframe(pd.DataFrame(data.data), use_container_width=True)
        else:
            st.warning("No history.")
