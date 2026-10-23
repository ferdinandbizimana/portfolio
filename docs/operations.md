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

## Running an analysis

1. **Data files**: upload the SAP exports (Excel or CSV). Large files are sent
   in pieces; if the connection drops, choose the same file again and the
   upload continues. Each file is read in the background and every sheet is
   matched to the kinds of file the analyses know.
2. **Analyses** → **Run**: give the run a name (e.g. "End of June 2026"),
   fill in the parameters (e.g. the period end) and choose the file and sheet
   for each input. Recognised sheets are chosen for you.
3. The run page follows the progress. If a file does not fit, nothing is
   calculated and each problem is listed with the file, sheet, row and column.
4. When it finishes: the checks (all must pass), the dashboard, and the Excel,
   Word and PowerPoint downloads.
5. **Runs**: tick two finished runs of the same analysis and **Compare** them
   (for example end of March against end of June).

Uploaded files and results are private. They are never shown on the public site.

### Closing stock by WBS

Files: the G/L line items of the stock accounts up to the period end, the MB51
list of expired stock scrapped at Finance level, and (optional) OX10 for plant
names. Parameter: the period end.

### RBC accountability report (each quarter)

Files: the previous RBC report (its "CPDS Report" sheet), the G/L line items
and the MB51 scrapping list (as for the closing stock), and optionally OX10
and the "ITEM Category" list. Parameters: opening date (e.g. 31 March 2026),
closing date (e.g. 30 June 2026), WBS element (RMS-PRG-FND-CP).

The report shows only opening stock, closing stock and the difference. Its
workbook contains a "CPDS Report" sheet in the same layout as the old one:
next quarter, upload this workbook as the previous report. Items seen for the
first time are put under CPDS and listed as "New item – assigned CPDS
(review)" so you can correct their programme in the ITEM Category list.

### Physical inventory variance investigation (after each count)

Files: the G/L line items of the stock adjustments posted after the count, with
the columns ACTION, REASON and Final Validation Status (and, if available, Root
cause and Required action); optionally the final closing stock per item and WBS
(sheet "Closing by ID and WBS" of the closing-stock-by-WBS workbook, or "Item
Detail by WBS" of the count findings workbook) for the inventory accuracy, and
the RBC report data sheet for the split by programme. Parameters: count date and
tolerance (0.005 = 0.5%).

## Report templates

In **Templates**, upload your Word (.docx) and PowerPoint (.pptx) templates and
click **Make active**. From then on every report uses them.

- **Word:** keep your cover, logo, header and footer. Put a paragraph that
  contains only `{{p body }}` where the report should go. You may also write
  `{{ title }}`, `{{ subtitle }}` and `{{ report_date }}` anywhere, for example
  on the cover page.
- **PowerPoint:** the layouts named "Title Slide", "Title and Content" and
  "Title Only" are used; the template's own example slides are left out.

If a template cannot be used, the run stops and says why. Reports are also
checked for the words "AI" and "to be confirmed"; a report containing them is
not produced.

## Publishing a dashboard

1. Open a finished run (Admin → Runs) and choose **Publish…**.
2. Give it a title and, if you like, a description. Choose **Summary only**
   (totals and summary tables, no line-level detail) or **Full detail**, and
   whether visitors see the self-checks. The preview below the form shows
   exactly what visitors will see.
3. **Create (private)** saves a frozen copy. Nobody else can see it yet.
4. In Admin → Published, choose who can see it:
   - **Secret link**: anyone with the link (`/d/…`). Not listed and not
     indexed by search engines. **New shared link** replaces it; the old
     link stops working at once.
   - **Public**: listed on the public Dashboards page with its own address
     (`/dashboards/…`).
5. **Unpublish** deletes the copy; every link to it stops working.

A publication never changes after it is created, even if you delete or
re-run the analysis. To update a published dashboard, publish the new run
and unpublish the old one.

## Shared folder and schedules

The app can pick up SAP exports from a folder instead of you uploading them.

1. In `.env`, set `INBOX_HOST_DIR` to the folder on the server, for example a
   network share mounted at `/mnt/sap-exports`. Default: `./local-data/inbox`.
   Restart with `docker compose up -d`. The app only reads this folder; it
   never changes or deletes anything in it.
2. Save exports there (sub-folders are fine). Every minute the scheduler takes
   files that have not changed for a minute (`INBOX_SETTLE_SECONDS`), so a
   file still being copied is left alone. They appear in Admin → Data files
   marked "from the shared folder". **Check the folder now** does it at once.
   A file saved again with the same content is not taken twice.
3. Admin → Schedules → **New schedule**:
   - the analysis;
   - when: at a set time on chosen days (in `TIMEZONE`, default
     Africa/Kigali), or as soon as new files arrive;
   - for each input, a file name pattern (`*` stands for any text, e.g.
     `MB52*.xlsx`); the newest ready file that matches is used;
   - dates such as the period end: "Last day of the previous month", "Day
     before the run", "Date of the run" or a fixed date. The run stores the
     actual date, so it can be repeated exactly;
   - "Skip the run when no file has changed", and "E-mail me when a run
     finishes" (sent to `NOTIFY_EMAIL`, or `CONTACT_TO_EMAIL` if empty).
4. **Run now** starts a run at once with the newest matching files. If a file
   is missing, the schedule says which one.

Deleting a schedule keeps its past runs.

## Server size

A file of about 5 million lines needs up to 2 GB of memory while it is
analysed. A server with 4 GB of memory is the minimum; 8 GB is comfortable.

## Checking the system

- Admin → **Overview** shows the database, the job queue, the worker, the
  scheduler, the last backup and the free disk space.
- `docker compose ps` lists the services and their health.
- `docker compose logs backend --tail 100` shows recent server messages.
- Errors of the last day:
  `docker compose logs --since 24h backend worker scheduler | grep '"ERROR"'`.
- Outside checks (uptime, backups) are described in [`deploy.md`](deploy.md).

## Updating

`scripts/update.sh` on the server: backup, latest version, rebuild, restart,
check. Database changes are applied automatically when the backend starts.

## Backups

Every night at `BACKUP_TIME` the `backup` service saves the database and the
stored files (uploads, reports, templates, portfolio files) to
`RESTIC_REPOSITORY`, encrypted with `RESTIC_PASSWORD`. It keeps 7 daily, 4
weekly and 12 monthly copies. The shared SAP folder is not included: it is
yours and stays where it is.

```bash
docker compose run --rm backup backup.sh           # a backup now
docker compose run --rm backup restic snapshots    # list the backups
docker compose logs backup --tail 50               # the last nightly run
```

## Restoring from a backup

This replaces the current database and files by those of the backup.

```bash
docker compose stop backend worker scheduler
docker compose run --rm backup restore.sh             # the latest backup
# or: docker compose run --rm backup restore.sh 1a2b3c4d   (a snapshot from the list)
docker compose up -d --wait
```

On a new server: install as in `deploy.md` with the **same** `.env` values for
`RESTIC_*` and `AWS_*`, run `docker compose up -d --wait`, then the three
commands above. Sign in with your usual password (it is restored too).

## Changing passwords and keys

| What | How |
|---|---|
| Your admin password | Admin → Settings, or `docker compose exec backend python -m app.cli set-password --email you@example.com`. All other sessions are signed out. |
| E-mail (SMTP) password | Create a new app password, put it in `.env` (`SMTP_PASSWORD`), `docker compose up -d`. Remove the old app password at the provider. |
| Database password | `docker compose exec postgres psql -U portfolio -c "ALTER USER portfolio PASSWORD 'new-value'"`, then the same value in `.env` (`POSTGRES_PASSWORD`), then `docker compose up -d`. |
| Backup bucket keys | Create new keys at the provider, put them in `.env` (`AWS_*`), `docker compose up -d`, delete the old keys. |
| Backup password | `docker compose run --rm backup restic key add` (enter the new one), put it in `.env`, `docker compose up -d`, then `restic key list` and `restic key remove <old id>`. Keep the new one in your password manager. |
| Secret dashboard links | Admin → Published → **New shared link** on each. |

