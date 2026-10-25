import os
import smtplib
from datetime import datetime, timezone
from pathlib import Path
from email.message import EmailMessage

import httpx
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from google import genai
from google.genai import errors as genai_errors
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import AuthApiError, AuthError, create_client
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

GEMINI_MODEL = "gemini-3.1-flash-lite"


def get_setting(name, default=""):
    environment_value = os.getenv(name)
    if environment_value:
        return environment_value

    try:
        secret_value = st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default

    return str(secret_value) if secret_value is not None else default


def get_supabase_client():
    client = st.session_state.get("supabase_client")
    if client is not None:
        return client

    url = get_setting("SUPABASE_URL")
    key = get_setting("SUPABASE_ANON_KEY")
    if not url or not key:
        raise ValueError(
            "Set SUPABASE_URL and SUPABASE_ANON_KEY in your local .env file."
        )

    client = create_client(url, key)
    st.session_state["supabase_client"] = client
    return client


def get_ai_answer(question):
    api_key = get_setting("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "Set GEMINI_API_KEY in your local .env file before asking AI."
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=question,
    )
    if not response.text:
        raise ValueError(
            "Gemini did not return a text answer. Try rephrasing your question."
        )
    return response.text


def get_owner_email():
    owner_email = get_setting("OWNER_EMAIL").strip().lower()
    if not owner_email:
        raise ValueError("Set OWNER_EMAIL in your .env or hosting settings.")
    return owner_email


def send_email(recipient, subject, body, reply_to=None):
    smtp_host = get_setting("SMTP_HOST").strip()
    smtp_username = get_setting("SMTP_USERNAME").strip()
    smtp_password = get_setting("SMTP_PASSWORD")
    from_email = get_setting("SMTP_FROM_EMAIL").strip() or smtp_username
    if not smtp_host or not smtp_username or not smtp_password or not from_email:
        raise ValueError(
            "Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and "
            "SMTP_FROM_EMAIL in your .env or hosting settings."
        )

    try:
        smtp_port = int(get_setting("SMTP_PORT", "465"))
    except ValueError as error:
        raise ValueError("SMTP_PORT must be a number, such as 465.") from error

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = recipient
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(body)

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


def get_questions(client, user_id):
    return (
        client.table("questions")
        .select(
            "id, user_id, user_email, question_type, question, answer, "
            "created_at, answered_at, read_at"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def show_data_error(error):
    if isinstance(error, PostgrestAPIError):
        st.error(
            "Supabase could not save or load question data. Make sure you ran "
            "the setup SQL in supabase_setup.sql and enabled the required "
            "database access policies."
        )
    elif isinstance(error, httpx.HTTPError):
        st.error("Could not reach Supabase. Check your internet connection.")
    else:
        st.error("Could not access Supabase question data. Please try again.")


def get_confirmation_redirect_url():
    app_url = get_setting("APP_URL").strip().rstrip("/")
    if not app_url:
        raise ValueError(
            "Set APP_URL to your app address in .env or your hosting settings."
        )
    if not app_url.startswith(("https://", "http://")):
        raise ValueError("APP_URL must start with https:// or http://.")
    return app_url


def normalize_email(email):
    email = email.strip().lower()
    parts = email.split("@")
    if (
        len(parts) != 2
        or not parts[0]
        or "." not in parts[1]
        or any(character.isspace() for character in email)
    ):
        return None
    return email


def show_supabase_error(error):
    if isinstance(error, ValueError):
        st.error(str(error))
    elif isinstance(error, AuthApiError):
        message = error.message
        if "already registered" in message.lower() or "already exists" in message.lower():
            st.error("An account with that email address already exists.")
        elif "invalid login credentials" in message.lower():
            st.error("Invalid email or password.")
        elif "redirect" in message.lower() or "url" in message.lower():
            st.error(
                "Supabase rejected the confirmation redirect URL. Add the app "
                "URL to Supabase Auth's allowed Redirect URLs."
            )
        else:
            st.error(f"Supabase could not complete the request: {message}")
    elif isinstance(error, (AuthError, httpx.HTTPError)):
        st.error(
            "Could not reach Supabase. Check your internet connection, project "
            "URL, and anon key in .env."
        )
    else:
        st.error(
            "Supabase could not complete the request. Check the project URL, "
            "anon key, and Auth settings in your Supabase dashboard."
        )


st.set_page_config(page_title="Ask Mahesh", page_icon="💬")

st.title("Ask Mahesh")
flash_notice = st.session_state.pop("flash_notice", None)
if flash_notice:
    if flash_notice[0] == "success":
        st.success(flash_notice[1])
    else:
        st.error(flash_notice[1])

logged_in_email = st.session_state.get("user_email", "")
if logged_in_email and (
    "supabase_client" not in st.session_state
    or "user_id" not in st.session_state
):
    st.session_state.pop("user_email", None)
    st.session_state.pop("user_id", None)
    st.session_state.pop("supabase_client", None)
    st.rerun()

logged_in_email = st.session_state.get("user_email", "")
owner_email = get_setting("OWNER_EMAIL").strip().lower()
is_owner = bool(
    logged_in_email and owner_email and logged_in_email.lower() == owner_email
)
pages = ["Log in / Sign up"]
if logged_in_email:
    pages.extend(["Ask a question", "My questions"])
    if is_owner:
        pages.append("Mahesh inbox")

page = st.sidebar.radio("Page", pages)
logged_in_email = st.session_state.get("user_email")

if logged_in_email:
    st.sidebar.caption(f"Logged in as {logged_in_email}")
    if st.sidebar.button("Log out"):
        try:
            st.session_state["supabase_client"].auth.sign_out()
            del st.session_state["user_email"]
            st.session_state.pop("user_id", None)
            del st.session_state["supabase_client"]
            st.rerun()
        except (AuthError, httpx.HTTPError, ValueError) as error:
            show_supabase_error(error)

if page == "Log in / Sign up":
    st.write("Sign in or create an account to use Ask Mahesh.")
    if logged_in_email:
        st.success(f"You are logged in as {logged_in_email}.")
    else:
        st.info("Create an account with your email address and a password.")

    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])

    with login_tab:
        st.subheader("Welcome back")
        with st.form("login_form"):
            login_email_input = st.text_input(
                "Email address",
                placeholder="you@example.com",
                key="login_email",
            )
            login_password = st.text_input(
                "Password",
                type="password",
                key="login_password",
            )
            login_submitted = st.form_submit_button("Log in")

        if login_submitted:
            email = normalize_email(login_email_input)
            if not email:
                st.error("Please enter a valid email address.")
            elif not login_password:
                st.error("Please enter your password.")
            else:
                try:
                    client = get_supabase_client()
                    response = client.auth.sign_in_with_password(
                        {"email": email, "password": login_password}
                    )
                    st.session_state["user_email"] = response.user.email
                    st.session_state["user_id"] = str(response.user.id)
                    st.rerun()
                except (ValueError, AuthError, httpx.HTTPError) as error:
                    show_supabase_error(error)

    with signup_tab:
        st.subheader("Create your account")
        with st.form("signup_form"):
            signup_email_input = st.text_input(
                "Email address",
                placeholder="you@example.com",
                key="signup_email",
            )
            signup_password = st.text_input(
                "Password",
                type="password",
                key="signup_password",
            )
            confirm_password = st.text_input(
                "Confirm password",
                type="password",
                key="confirm_password",
            )
            signup_submitted = st.form_submit_button("Create account")

        if signup_submitted:
            email = normalize_email(signup_email_input)
            if not email:
                st.error("Please enter a valid email address.")
            elif len(signup_password) < 8:
                st.error("Choose a password with at least 8 characters.")
            elif signup_password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    redirect_url = get_confirmation_redirect_url()
                    client = get_supabase_client()
                    response = client.auth.sign_up(
                        {
                            "email": email,
                            "password": signup_password,
                            "options": {
                                "email_redirect_to": redirect_url
                            },
                        }
                    )
                    if response.user and response.user.identities == []:
                        st.error("An account with that email address already exists.")
                    elif response.session is None:
                        st.success(
                            "Account created. Check your email for a confirmation "
                            "link, then log in."
                        )
                    else:
                        st.session_state["user_email"] = email
                        st.session_state["user_id"] = str(response.user.id)
                        st.rerun()
                except (ValueError, AuthError, httpx.HTTPError) as error:
                    show_supabase_error(error)

elif page == "Ask a question":
    st.write("Ask Gemini or send a question privately to Mahesh.")
    st.header("Ask a question")

    with st.form("question_form"):
        question_type = st.radio(
            "Who should answer?",
            ["#AI", "#mahesh"],
            horizontal=True,
        )
        question = st.text_area(
            "Your question",
            placeholder="Write your question here",
            max_chars=4000,
        )
        question_submitted = st.form_submit_button("Submit question")

    if question_submitted:
        cleaned_question = question.strip()
        if not cleaned_question:
            st.error("Please enter a question.")
        elif not st.session_state.get("user_id"):
            st.error("Please log in again before submitting a question.")
        else:
            client = st.session_state["supabase_client"]
            if question_type == "#AI":
                with st.spinner("Gemini is thinking..."):
                    try:
                        answer = get_ai_answer(cleaned_question)
                    except ValueError as error:
                        st.error(str(error))
                    except genai_errors.APIError as error:
                        if error.code == 429:
                            st.error(
                                "Gemini's free-tier request limit may have been "
                                "reached. Check your Google AI Studio quota and "
                                "try again later."
                            )
                        else:
                            st.error(
                                "Gemini could not answer this question. Check "
                                "your API key, model access, and Google AI Studio "
                                "usage limits."
                            )
                    except httpx.HTTPError:
                        st.error(
                            "Could not reach Gemini. Check your internet "
                            "connection and try again."
                        )
                    else:
                        try:
                            client.table("questions").insert(
                                {
                                    "user_id": st.session_state["user_id"],
                                    "user_email": logged_in_email,
                                    "question_type": "ai",
                                    "question": cleaned_question,
                                    "answer": answer,
                                    "answered_at": datetime.now(timezone.utc).isoformat(),
                                }
                            ).execute()
                            st.success("Gemini's answer")
                            st.markdown(answer)
                            st.caption("Saved in My questions.")
                        except (PostgrestAPIError, httpx.HTTPError) as error:
                            st.error(
                                "Gemini answered, but the question could not be "
                                "saved. Please check the Supabase setup."
                            )
                            st.markdown(answer)
                            show_data_error(error)
            else:
                try:
                    client.table("questions").insert(
                        {
                            "user_id": st.session_state["user_id"],
                            "user_email": logged_in_email,
                            "question_type": "mahesh",
                            "question": cleaned_question,
                        }
                    ).execute()
                except (PostgrestAPIError, httpx.HTTPError) as error:
                    show_data_error(error)
                else:
                    try:
                        owner = get_owner_email()
                        send_email(
                            owner,
                            "New Ask Mahesh question",
                            (
                                f"{logged_in_email} asked Mahesh:\n\n"
                                f"{cleaned_question}\n\n"
                                "Sign in to Ask Mahesh and open the Mahesh inbox "
                                "to reply."
                            ),
                            reply_to=logged_in_email,
                        )
                    except (ValueError, smtplib.SMTPException, OSError) as error:
                        if isinstance(error, ValueError):
                            st.error(str(error))
                        else:
                            st.error(
                                "Your question was saved, but the email alert "
                                "could not be sent. Check the Gmail SMTP settings."
                            )
                    else:
                        st.success(
                            "Your question was sent to Mahesh. You’ll find replies "
                            "in My questions."
                        )

elif page == "My questions":
    st.header("My questions and answers")
    try:
        questions = get_questions(
            st.session_state["supabase_client"],
            st.session_state["user_id"],
        )
    except (PostgrestAPIError, httpx.HTTPError) as error:
        show_data_error(error)
    else:
        if not questions:
            st.info("You have not asked any questions yet.")
        for row in questions:
            unread = (
                row["question_type"] == "mahesh"
                and row["answered_at"] is not None
                and row["read_at"] is None
            )
            title = f"{'#AI' if row['question_type'] == 'ai' else '#mahesh'} · {row['created_at']}"
            if unread:
                title = "🔔 New answer · " + title
            with st.expander(title, expanded=unread):
                st.markdown("**Your question**")
                st.write(row["question"])
                if row["answer"]:
                    st.markdown("**Answer**")
                    st.markdown(row["answer"])
                    if unread:
                        if st.button("Mark answer as read", key=f"read_{row['id']}"):
                            try:
                                st.session_state["supabase_client"].rpc(
                                    "mark_question_read",
                                    {"p_question_id": row["id"]},
                                ).execute()
                            except (PostgrestAPIError, httpx.HTTPError) as error:
                                show_data_error(error)
                            else:
                                st.rerun()
                elif row["question_type"] == "mahesh":
                    st.info("Mahesh has not replied yet.")

elif page == "Mahesh inbox" and is_owner:
    st.header("Mahesh’s private inbox")
    try:
        rows = (
            st.session_state["supabase_client"]
            .table("questions")
            .select("id, user_email, question, answer, created_at, answered_at")
            .eq("question_type", "mahesh")
            .order("created_at", desc=True)
            .execute()
            .data
        )
    except (PostgrestAPIError, httpx.HTTPError) as error:
        show_data_error(error)
    else:
        if not rows:
            st.info("There are no questions for Mahesh yet.")
        for row in rows:
            status = "Answered" if row["answer"] else "Waiting for your reply"
            with st.expander(
                f"{status} · {row['user_email']} · {row['created_at']}",
                expanded=not bool(row["answer"]),
            ):
                st.markdown("**Question**")
                st.write(row["question"])
                if row["answer"]:
                    st.markdown("**Current answer**")
                    st.markdown(row["answer"])
                with st.form(f"reply_form_{row['id']}"):
                    reply = st.text_area(
                        "Your answer",
                        value=row["answer"] or "",
                        key=f"reply_{row['id']}",
                    )
                    reply_submitted = st.form_submit_button("Send answer")

                if reply_submitted:
                    if not reply.strip():
                        st.error("Please write an answer before sending.")
                    else:
                        try:
                            st.session_state["supabase_client"].rpc(
                                "owner_reply_to_question",
                                {
                                    "p_question_id": row["id"],
                                    "p_answer": reply.strip(),
                                },
                            ).execute()
                        except (PostgrestAPIError, httpx.HTTPError) as error:
                            show_data_error(error)
                        else:
                            try:
                                send_email(
                                    row["user_email"],
                                    "Mahesh answered your question",
                                    (
                                        "Mahesh has answered your question.\n\n"
                                        f"Your question:\n{row['question']}\n\n"
                                        "Mahesh's answer:\n"
                                        f"{reply.strip()}\n\n"
                                        "Sign in to Ask Mahesh to view your answer "
                                        "and mark it as read."
                                    ),
                                )
                            except (ValueError, smtplib.SMTPException, OSError) as error:
                                if isinstance(error, ValueError):
                                    st.session_state["flash_notice"] = (
                                        "error",
                                        f"The answer was saved, but {error}",
                                    )
                                else:
                                    st.session_state["flash_notice"] = (
                                        "error",
                                        "The answer was saved, but the email "
                                        "notification could not be sent. Check "
                                        "the Gmail SMTP settings.",
                                    )
                            else:
                                st.session_state["flash_notice"] = (
                                    "success",
                                    "Answer saved and email sent to the user.",
                                )
                            st.rerun()
