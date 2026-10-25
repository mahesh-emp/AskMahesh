# Ask Mahesh

A beginner Python project built with Streamlit. Signup and login use Supabase
Auth with email and password. Supabase stores and securely hashes account
passwords; this app does not connect directly to PostgreSQL or handle password
hashes. Signed-in users can ask `#AI` questions and receive answers from
Gemini, or send `#mahesh` questions to Mahesh. Supabase stores questions and
answers, and users can see their own history and unread replies.

## 1. Create a Supabase project

Create a project at https://supabase.com, then find its project URL and a
publishable key (or legacy `anon` key) in the project's API settings. These
values are intended for client use. Never use a `service_role` or secret key
in this app.

Supabase may require users to confirm their email before they can log in. If
you want to test without confirmation emails, adjust the email confirmation
setting in your Supabase project's Auth settings. Otherwise, check the signup
email and follow the confirmation link.

## 2. Configure local settings

Copy `.env.example` to `.env`, then open `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace the example URL and key with your Supabase project's URL and
publishable/anon key. Set `APP_URL` to the address where users will open your
app. For local testing, use `http://localhost:8501`. In production, use your
deployed HTTPS address, such as `https://your-app.example.com`. The app
requires this setting and does not silently fall back to localhost.
Keep `.env` private; it is excluded from Git. Do not put real keys in
`.env.example` or in the Python source.

## 3. Allow the confirmation redirect in Supabase

In the Supabase dashboard, open **Authentication → URL Configuration**:

1. Set **Site URL** to your production app's HTTPS address.
2. Add that same address under **Redirect URLs** and save.

The app also sends this address with each signup as its email confirmation
redirect. The address in `APP_URL`, Site URL, and the allowed Redirect URLs
must match. During local development, you can add `http://localhost:8501` as
an additional allowed Redirect URL and set `APP_URL` to that local address in
your local `.env`. For production, configure `APP_URL` as a hosting
environment variable with your deployed HTTPS address; do not use localhost.

## 4. Install and run on Windows PowerShell

The project currently has a virtual environment named `envi`. From the project
folder, run:

```powershell
.\envi\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

If `envi` does not exist, create it first:

```powershell
python -m venv envi
.\envi\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

The app should open at http://localhost:8501. For local testing, set
`APP_URL=http://localhost:8501` in `.env` and allow that URL in Supabase.
Sign up with an email and password, confirm the email if required by your
Supabase settings, and then log in. After login, use the sidebar to open the
question form or your question history.

## 5. Set up the questions database and owner access

In the Supabase dashboard, open **SQL Editor**, create a query, paste the
contents of `supabase_setup.sql`, and run it. This creates the questions
table, row-level security policies, and two restricted functions for owner
replies and marking answers as read.

The SQL policy grants the private Mahesh inbox to exactly
`mahi.eduu@gmail.com`. Create/sign up for a Supabase Auth account with this
email, and set `OWNER_EMAIL=mahi.eduu@gmail.com` in `.env`. If you change the
owner email later, update the matching email in `supabase_setup.sql` and run
that SQL again. Do not use a Supabase service-role key in the app.

## 6. Set up Gmail notifications

Use a Gmail account to send low-volume demo notifications. Turn on 2-Step
Verification for that Google account and create a Google **App Password**.
Use the App Password in `SMTP_PASSWORD` (not your regular Gmail password):

```text
OWNER_EMAIL=mahi.eduu@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your-sending-gmail-address
SMTP_PASSWORD=your-google-app-password
SMTP_FROM_EMAIL=your-sending-gmail-address
```

When someone submits a `#mahesh` question, the app saves it in Supabase and
sends a notification to `OWNER_EMAIL`. Sign in to the app using the owner
account to open **Mahesh inbox** and reply. The reply is saved and emailed to
the user. The user can read it in **My questions** and mark it as read; unread
answers are highlighted there.

If an email fails after a question or answer is saved, the page says that the
data was saved but the email notification failed. Check the SMTP settings and
mail provider limits. Do not put Gmail or Supabase secrets into source files,
browser-visible UI, or `.env.example`.

## 7. Set up Gemini AI answers

Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey)
and add it to your private `.env` file:

```text
GEMINI_API_KEY=your-key-from-google-ai-studio
```

Restart Streamlit after editing `.env`. When logged in, select `#AI`, enter a
question, and submit it. The key is used by the Python app server and is not
shown in the page. Never paste it into the app UI, source code, or
`.env.example`.

The app currently calls Google's `gemini-3.1-flash-lite` model. Google offers
a free tier for certain Gemini API models, but model eligibility, per-minute
and daily request quotas, supported regions, and pricing can change. Check the
[current Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) for your
account before relying on it. Prompts submitted to the Gemini free tier may
be handled under Google's free-tier data-use terms; avoid sending private or
sensitive information.

## Production configuration

The app reads settings from local `.env` while developing, and from Streamlit
secrets when deployed. For Streamlit Community Cloud:

1. Push the project to a GitHub repository. Confirm `.env` is not committed.
2. Deploy `app.py` from that repository at
   [Streamlit Community Cloud](https://share.streamlit.io/).
3. Open your deployed app's **Settings → Secrets** and paste TOML in this
   format, replacing every placeholder with your own values:

   ```toml
   SUPABASE_URL = "https://your-project-id.supabase.co"
   SUPABASE_ANON_KEY = "your-supabase-anon-or-publishable-key"
   APP_URL = "https://your-app-name.streamlit.app"
   GEMINI_API_KEY = "your-google-ai-studio-api-key"
   OWNER_EMAIL = "mahi.eduu@gmail.com"
   SMTP_HOST = "smtp.gmail.com"
   SMTP_PORT = "465"
   SMTP_USERNAME = "your-sending-gmail-address"
   SMTP_PASSWORD = "your-google-app-password"
   SMTP_FROM_EMAIL = "your-sending-gmail-address"
   ```

4. Set `APP_URL` to the actual Streamlit app URL, then add that same URL to
   Supabase **Authentication → URL Configuration** as the Site URL and an
   allowed Redirect URL.
5. Save the secrets and reboot/redeploy the app.

The app checks environment variables first, then Streamlit secrets. Keep
`.env` and deployed secrets private, and never add a Supabase service-role key
to the app. If you change your deployed domain later, update `APP_URL` and the
Supabase URL configuration too.

Accounts from the earlier local PostgreSQL version are not automatically
migrated; they need to sign up again in Supabase. The app uses Supabase Auth's
managed user store and does not create a local `app_users` table. The SQL
policies ensure users can read only their own questions, while only the
configured owner can view and answer Mahesh questions.
