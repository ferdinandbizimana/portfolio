# Getting started: step by step (for beginners)

This guide takes you from a switched-off computer to a working application, in
order. Follow the steps from top to bottom. The commands are for **Windows
PowerShell** on your own computer.

This file is in the project at `docs/getting-started.md`, so it is always
with the code. More detail on each page of the application is in
[`operations.md`](operations.md); the project status is in [`PLAN.md`](PLAN.md).

---

## Part A: what you need (once)

### A1. Programs on your computer

| Program | What it is for | Check it is installed (PowerShell) |
|---|---|---|
| **Docker Desktop** | Runs the whole application (database, website, workers) | `docker --version` |
| **Git** | Downloads the code and its updates from GitHub | `git --version` |
| **Claude Code** (optional) | Lets Claude work on the project on your computer | `claude --version` |

Each command should print a version number. If one says "not recognized",
install that program and open a **new** PowerShell window.

### A2. Accounts and credentials

Write these in a password manager (or a notebook kept safe). **Never** put real
passwords in this file, in the code, in a chat or in an e-mail.

| Credential | What it is for | Where it is stored |
|---|---|---|
| **GitHub account** `ferdinandbizimana` | The code lives at github.com/ferdinandbizimana/portfolio | github.com |
| **Claude account** | Claude Code on your computer, and claude.ai/code | claude.ai |
| **Admin e-mail and password** of the application | Signing in at http://localhost:8080/admin | Your password manager; first set in the `.env` file (`ADMIN_EMAIL`, `ADMIN_PASSWORD`). The password needs **at least 12 characters**. |
| **Database password** | Used by the application internally; you never type it | `.env` file (`POSTGRES_PASSWORD`) |
| **E-mail (SMTP) account** (optional) | Sending real e-mails: contact form, variance and expiry e-mails | `.env` file (`SMTP_...`, `MAIL_FROM`) |

The `.env` file is a settings file inside the project folder. It holds the
passwords, so it is **never** uploaded to GitHub (Git ignores it). If you
lose your computer, you lose this file: keep its values in your password
manager.

---

## Part B: the first time on a computer

Skip Part B if the project already runs on this computer.

### B1. Choose where the project lives

The usual place is your user folder: `C:\Users\<your Windows name>\portfolio`.

1. Open **PowerShell** (Start menu, type "PowerShell").
2. Go to your user folder and download the project:

   ```powershell
   cd $HOME
   git clone https://github.com/ferdinandbizimana/portfolio.git
   cd portfolio
   ```

   If Git asks you to sign in, sign in with your GitHub account.

### B2. Create the settings file `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

In Notepad, fill in at least these lines, then save and close:

```
POSTGRES_PASSWORD=<invent a long password; you never need to type it again>
ADMIN_EMAIL=<the e-mail you will sign in with>
ADMIN_PASSWORD=<your admin password, at least 12 characters>
```

Leave everything else as it is for now. To test e-mails without sending real
ones, also set these four lines (the e-mails then appear at
http://localhost:8025 instead of being sent):

```
COMPOSE_PROFILES=dev-mail
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_SECURITY=none
MAIL_FROM=stock@example.com
```

### B3. Continue with Part C

The admin account is created automatically the first time the application
starts, from `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

---

## Part C: every time you want to use or continue the project

### C1. Start Docker Desktop

Open **Docker Desktop** from the Start menu and wait until it says it is
running (the whale icon in the taskbar stops moving). Nothing else works
without it.

### C2. Open PowerShell in the project folder

```powershell
cd $HOME\portfolio
```

**Can't remember where the project is?** This searches your user folder:

```powershell
Get-ChildItem -Path $HOME -Filter portfolio -Directory -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object FullName
```

The right folder is the one that contains `docker-compose.yml`. Check with:

```powershell
Test-Path .\docker-compose.yml    # must print True
```

### C3. Get the latest changes

```powershell
git pull
```

"Already up to date." means you have everything. Otherwise it lists the
files that changed.

### C4. Start (or update) the application

```powershell
docker compose up --build -d
```

- `--build` rebuilds the application with the latest changes. The first time,
  or after big changes, this takes **10 to 20 minutes**; later it is quicker.
- `-d` runs it in the background, so you get the PowerShell prompt back when it
  has started.

### C5. Check that it is running

```powershell
docker compose ps
```

Every line should say `running` or `healthy`. Then open
http://localhost:8080/api/health in your browser: it shows `"status":"ok"`.

If a line says `restarting` or `exited`, see what went wrong:

```powershell
docker compose logs backend --tail 50
```

### C6. Open the application

| Address | What it is |
|---|---|
| http://localhost:8080 | The public portfolio |
| http://localhost:8080/admin | The private area: sign in with your admin e-mail and password |
| http://localhost:8025 | Test mailbox (only with the `dev-mail` settings of B2) |

### C7. Check which version of an analysis you are looking at

Results are saved when a run finishes and **never change by themselves**. After
an update (C3–C4), open the run and click **Run again**: it uses the same files
and parameters with the newest version of the analysis. The version is shown
next to the analysis name at the top of the run page (for example
"Stock in transit v1.4.0"). **Change and run again** opens the form filled in,
to change a date or a file first.

### C8. Stop the application when you are done

```powershell
docker compose down
```

Your data (files, runs, accounts) is **kept** and comes back at the next
`docker compose up -d`.

> **Warning:** `docker compose down -v` (with `-v`) **deletes all data**: uploaded
> files, runs and the admin account. Only use it to start again from empty.

---

## Part D: working in the application (short version)

1. **Data files** → upload the SAP exports (Excel or CSV).
2. **Analyses** → choose an analysis → **Run**: give it a name, check the
   dates and the files, click **Run analysis**.
3. The run page shows progress, then the checks (all must pass), the dashboard,
   and the **Downloads** list (Excel, Word, PowerPoint, HTML dashboard).
4. **Run again** / **Change and run again** on a finished run (see C7).
5. **Stock variances** and **Expiry follow-up** have their own pages; see
   [`operations.md`](operations.md).

**Fake data to try everything** (only on a test installation):

```powershell
docker compose exec backend python -m app.cli seed-demo
```

---

## Part E: continuing development with Claude

### On your computer (Claude Code)

```powershell
cd $HOME\portfolio
claude
```

Then tell Claude what you want, for example: *"Read docs/PLAN.md and
continue from Next"* or *"In stock in transit, …"*. Claude reads `CLAUDE.md`
(the project rules) by itself.

### In the browser (claude.ai/code)

Open a session on the repository `ferdinandbizimana/portfolio`. When the work
is merged on GitHub, bring it to your computer with C3 and C4.

### The usual cycle of a change

1. You describe the change (in Claude Code or claude.ai/code).
2. Claude changes the code, runs the tests, and opens a **pull request** on GitHub.
3. GitHub runs all the tests again. When they pass, the change is merged into
   `main`.
4. On your computer: **C3** (`git pull`) and **C4** (`docker compose up --build -d`).
5. In the application: **Run again** on the runs you want recalculated.

---

## Part F: when something goes wrong

| Problem | What to do |
|---|---|
| `docker: error during connect` / "cannot find the file specified" | Docker Desktop is not running: do C1, wait, try again. |
| `'claude' is not recognized` | Close PowerShell and open a new one; if it persists, reinstall Claude Code. |
| `git pull` says "not a git repository" | You are not in the project folder: do C2. |
| `git pull` says "Your local changes would be overwritten" | Ask Claude Code: "git pull fails with local changes, help me". Do not delete files yourself. |
| Forgot the admin password | `docker compose exec backend python -m app.cli set-password --email <your admin e-mail>` (it asks for the new password, at least 12 characters). |
| "The password must have at least 12 characters." | Choose a longer password. |
| The page shows old figures after an update | Open the run and click **Run again** (C7). |
| Port 8080 is already in use | Another program uses it; restart the computer, or stop the other program. |
| The build is very slow | Normal the first time (up to 20 minutes). Leave it running. |
| Anything else | `docker compose logs backend --tail 50`, copy the output into Claude Code and ask what it means. |

---

## Part G: where things are

| Thing | Where |
|---|---|
| Project folder on your computer | Usually `C:\Users\<your Windows name>\portfolio` (find it with C2) |
| Code on the internet | https://github.com/ferdinandbizimana/portfolio |
| Settings and passwords | `.env` in the project folder (never on GitHub) |
| Uploaded files, runs, accounts | Inside Docker (volumes), kept between restarts |
| Project plan, decisions, open questions | `docs/PLAN.md` |
| How each page works | `docs/operations.md` |
| Putting the site on a server with the domain | `docs/deploy.md` |
| SAP exports each analysis needs | `docs/sap-exports.md` |
| Rules for Claude and developers | `CLAUDE.md` |
