# Operations guide

How to run and look after the application. Commands are run on the server (or
your computer), in the project folder. Phase 9 adds deployment, backups and
restore to this guide.

## First start

```bash
cp .env.example .env          # then edit .env (at least POSTGRES_PASSWORD)
docker compose up -d --build
docker compose exec backend python -m app.cli create-admin --email you@example.com
```

Open the site (locally http://localhost:8080) and sign in at `/admin`.

## Forgotten password

```bash
docker compose exec backend python -m app.cli set-password --email you@example.com
```

All your other sessions stay signed in until they expire; to sign everything
out, change the password again from **Settings** once you are back in.

## Contact form e-mail

The contact form sends each message to your inbox by SMTP. Set these lines in
`.env`, then restart with `docker compose up -d`:

| Setting | Meaning |
|---|---|
| `CONTACT_TO_EMAIL` | Where messages arrive (your address). |
| `MAIL_FROM` | Sender address shown on the messages. With Gmail, use the same Gmail address. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` | Your provider's outgoing server. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Your provider's login for sending. |

**Gmail example**

1. Turn on 2-Step Verification for the Google account (required for app passwords).
2. Create an app password: Google Account → Security → App passwords. Copy the 16 letters.
3. In `.env`:

   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_SECURITY=starttls
   SMTP_USERNAME=your.address@gmail.com
   SMTP_PASSWORD=the 16-letter app password
   MAIL_FROM=your.address@gmail.com
   CONTACT_TO_EMAIL=your.address@gmail.com
   ```

4. Restart, then in the admin area open **Settings → Send a test e-mail**.

When a visitor writes, you receive an e-mail whose **Reply** goes straight to
the visitor. Each address can send at most 5 messages per hour, and a hidden
field stops most spam robots.

**Testing without sending real e-mail:** add `COMPOSE_PROFILES=dev-mail` and
set `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_SECURITY=none`. Messages are
caught and shown at http://localhost:8025.

## Editing the portfolio

Everything on the public site is edited in the admin area: **Profile**
(name, introduction, photo, CV), **Experience**, **Skills** and **Projects**.
Changes appear on the public site as soon as you save. A project is visible
only when **Published** is ticked.

Long texts use Markdown: `**bold**`, `*italic*`, `## Heading`, `- list item`,
`[link text](https://…)` and tables. Use **Preview** to check before saving.

## Checking the system

- The admin **Overview** shows whether the database and the job queue are running.
- `docker compose ps` lists the services and their health.
- `docker compose logs backend --tail 100` shows recent server messages.
