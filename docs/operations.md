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

Or let the start create the account: set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (at
least 12 characters) in `.env` before `docker compose up`. The account is made
only when the database has none; `.env` never goes to git. Change the password
later with `set-password` (below), not by editing these lines.

Open the site (locally http://localhost:8080) and sign in at `/admin`.

## Test data (demo)

To try every page before using real files, fill a test installation with fake
data:

```bash
docker compose exec backend python -m app.cli seed-demo
```

In about a minute it adds:
- a sample portfolio (profile, experience, skills, three projects), only when the
  portfolio is empty; replace the text marked "(sample)" before going live;
- 24 data files named `DEMO_...` (GL lines, MB51, ZSTOCKREPORT snapshots, VA05,
  deliveries, ME2M, MB5T, EWM tasks, weekly report, picking register, spot checks,
  bin list, donations and the others), with invented materials, plants,
  customers and figures;
- one run of every analysis on those files (all self-checks pass), the stock
  variances from the two spot checks and the expiry follow-up of the expiry run.

Running it again keeps the portfolio and the files and adds another set of runs.
It refuses to run when `ENVIRONMENT=production`. The public pages are cached for
up to 10 minutes: `docker compose restart frontend` shows the sample portfolio at
once. To start again from empty: `docker compose down -v` (this deletes all
data of the installation), then `docker compose up -d`.

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
5. **Run again**: on a finished run, "Run again" starts a new run on the same
   files, sheets and parameters with the current version of the analysis (for
   example after a correction of its rules); the earlier run is kept.
   "Change and run again" opens the form filled in from the run, to change a
   parameter or a file first. A run's results never change by themselves: after
   an update of the application, run it again to see the new figures (the run
   page shows the version it was calculated with).
6. **Runs**: tick two finished runs of the same analysis and **Compare** them
   (for example end of March against end of June).

Uploaded files and results are private. They are never shown on the public site.

### Closing stock by WBS

Files: the G/L line items of the stock accounts up to the period end, the MB51
list of goods movements (MB51), and (optional) OX10 for plant names and the
"Closing vs Counted branches" sheet to compare counted stock with the final
closing. Parameters: the period end and the MB51 movement types that count as
expired stock scrapped (551, 555 by default; other MB51 lines are left out and
counted in the run).

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

### Stock count reconciliation (after each count)

File: the "Closing vs Counted branches" sheet of the reconciliation workbook
(closing posted in Finance, counted quantity and value, difference, reason),
and optionally OX10 for plant names. Parameter: the count date. Each line with
a difference gets a cause from its reason; lines whose value does not match
quantity × unit cost, "NO VARIANCE" lines with a difference and materials whose
differences offset across plants are flagged.

### Stock sufficiency against AMC (weekly or each quarter)

Files: the weekly stock monitoring workbook (every programme sheet is read;
sheets without the product table are skipped), ZSTOCKREPORT (links the weekly
product codes to SAP materials through "NPC CODE", otherwise through the
description) and, optionally, the final closing stock by WBS (sheet "Final
Closing Stock" of the closing-stock workbook) to value the stock at closing as
in the RBC report. Without it, the value is ZSTOCKREPORT quantity × unit cost.
Parameters: the weekly report date and the WBS element. Weekly products that
no SAP material matches are listed in the workbook ("Not linked to SAP").

### Physical inventory variance investigation (after each count)

Files: the G/L line items of the stock adjustments posted after the count, with
the columns ACTION, REASON and Final Validation Status (and, if available, Root
cause and Required action); optionally the final closing stock per item and WBS
(sheet "Closing by ID and WBS" of the closing-stock-by-WBS workbook, or "Item
Detail by WBS" of the count findings workbook) for the inventory accuracy, and
the RBC report data sheet for the split by programme. Parameters: count date and
tolerance (0.005 = 0.5%).

### Interactive dashboards (every analysis)

Every run gives at least an **Excel workbook** and an **interactive dashboard**
(HTML), whatever the analysis. Every run also gives an **interactive dashboard**: the button "Open interactive
dashboard" on the run page opens it, and it is listed with the reports as one
HTML file you can download, keep and e-mail (it opens offline in any recent
browser; the data is inside the file). Filters at the top apply to every
section unless a section says otherwise; tables have totals; the detailed lines
can be searched and downloaded as CSV. The self-checks are at the bottom. The
variance investigation shows inventory accuracy before and after justification;
the RBC dashboard shows only opening stock, closing stock and the difference.

### Order fill rate

Files: VA05 sales orders and the list of outbound deliveries (optionally OX10
for plant and customer names, districts and regions; MB51 for the value of
programme (ZDON) distributions). Parameters: first and last order date, whether
only goods-issued deliveries count (default yes) and the border districts. Shows lines and orders delivered
in full, quantity and value fill rate by delivering plant, customer and month.

The run also gives an **interactive dashboard** (button "Open interactive
dashboard" on the run page; also downloadable as one HTML file that opens
offline in any recent browser and can be e-mailed). It follows the layout of
the "RMS Order Fill Rate Dashboard": loss per WBS (RMS-OWN-ESE-RM in RWF, donor
RMS-PRG-FND-CP in units), monthly trend, financial quarters, plants, items most
requested and not delivered, most-missing items over time, Delivered-In-Full
by order and customer, regional analysis (region, district, border districts,
facility type) and every order line (with CSV download). Filters: quarter,
month, plant, WBS, order type, customer, item, region, district, border
district and facility type; they apply to every section unless the section
says otherwise. If the VA05 export has the "Plant" column it gives each line's
plant; otherwise the delivering plant (or the plant that usually serves the
customer) is used.

### Expiry monitoring and the monthly follow-up

Files: the ZSTOCKREPORT of the opening month and the one of the closing month of
a period (a month, a quarter, six months or the financial year: the two dates
decide), optionally MB51 (with batches: distributions and scrapping) and OX10.
Parameters: the two dates, the quarantine plants (codes or starts of codes;
default 9900, the RMS quarantine plant), the distribution and
scrapping movement types and the short shelf life (3 months).

It shows the expired stock per plant (and expired batches not blocked or outside
the quarantine plant), the batches that were due to expire in the period and
whether they were cleared or expired (projected minus expired = value saved),
the 3- and 6-month outlook, batches whose expiry date changed, distributions with
less than 3 months of shelf life (for a 641, what became of the batch at the
receiving plant) and the days from expiry to scrapping. Commercial stock is on
RMS-OWN WBS elements, programme stock on RMS-PRG. The interactive dashboard has
the board views per plant (executive expiry outlook, intervention and savings,
expired stock per plant).

Donations: add Sales' list of donated products (the ZSTOCKREPORT lines of those
products with Total Value, Status, Customer and Reason for Donation) as the
optional "Donations to save expiries" input. Lines whose status is not
"donated" are listed but not counted; donated batches that were due to expire
in the period are shown as saved by donation.

**Expiry follow-up** (admin menu): for each run, "Prepare the follow-up" lists the
expired items and the items expiring within 6 months. The sales pharmacist opens
the secure link (no account), records for each item expiring soon the measure
taken to avoid the expiry (redistribution, transfer, donation, sale, ...; "Other"
needs it described), chooses the root cause of each expired item ("Other" needs
the reason written out) and saves each one. On the last day of each month, from `EXPIRY_MAIL_TIME`, the latest run
is e-mailed to `EXPIRY_MAIL_TO`, copied to `EXPIRY_MAIL_CC` and `EXPIRY_MAIL_BCC`:
expired, within 3 months and 3 to 6 months, value per plant, with the batches in
Excel and the link. "Send the e-mail now" sends it at once. The justifications and
measures can be downloaded as Excel (one sheet each) and as the justifications dashboard (commercial and
programme loss, root causes, top 20 of each with their reasons).

### Expiry risk

Files: ZSTOCKREPORT (batches with expiry dates) and the weekly stock monitoring
workbook (AMC), optionally OX10. Parameters: stock report date and, if wanted,
one WBS element. Shows stock by expiry band and the value that cannot be used
before expiry at the AMC, and months of stock against remaining shelf life per
material and WBS: overstock (stock left at expiry, value at risk) or risk of
stockout (stock runs out before it expires).

### Stock in transit

Files: MB5T and MB51 (the goods movements for the period of the transfers;
MB51 must include the columns Purchase order, Reference and Posting Date),
optionally ME2M (STO creation dates) and OX10. Parameters: MB5T date and the "long transit" limit in days.
Every MB5T line is counted (the number of lines matches the MB5T document). When
MB5T gives no value for a line, the value is taken from the goods issue (641) of
the outbound delivery in MB51 for the quantity still in transit; the "Value from"
column says which.

### Purchase order follow-up

Files: ME2N and the list of inbound deliveries, optionally OX10. Parameters:
first and last PO creation date and the report date. Shows the delivery period
from PO creation to goods receipt and what was delivered in full.

### Warehouse activity

Files: EWM "All Movement for Products" (warehouse tasks), the list of outbound
deliveries (picking to goods issue) and MB51 (to flag EWM deliveries whose
goods receipt or goods issue is missing in ERP). Parameters: report date and the
dock-to-stock target in days.

## Stock variance follow-up

Admin → Stock variances.

1. **Bin list** (once, and whenever it changes): upload the list of storage bins
   with their responsible person on Data files, then choose it under "Bin list"
   and click Import bin list. The e-mails are taken from the rows below the bins
   (name, e-mail); you can correct an e-mail on the page. Bins given to a unit
   name (RECEIVING, PICKING; set in `VARIANCE_UNIT_NAMES`) get no variances.
2. **Variances**: upload the weekly spot check, the picking register or the PI
   document, choose it under "Variance file" and click Create variances. Each line
   with a difference goes to the person responsible for its bin; lines already
   imported are not created twice.
3. When the day closes (`VARIANCE_DAY_CLOSE_TIME`, default 17:00) each person
   receives one e-mail with all their new variances of the day, a link per
   variance. To send them earlier, click "Send e-mails now". The link opens a page
   (no login) where they record the root cause (from the list), the reason, the
   quantity corrected (optional), the responsible unit, the action taken and their
   name; the variance is then marked corrected. Every working morning (`VARIANCE_REMINDER_TIME`) each person
   receives the list of their open variances; open for more than
   `VARIANCE_OVERDUE_DAYS` days is red. Every e-mail goes in BCC to `VARIANCE_BCC`.
4. On the page you can reassign a variance (the new person gets it with the next
   e-mail), mark it corrected yourself, reopen it, copy its link, and download the
   Excel list.
5. **Accuracy progress**: one line per imported file, with line and quantity
   accuracy when it was imported and now (only the variances still open count),
   so each correction shows. It is also a sheet of the Excel list.

### Picker accuracy

File: the picking register (its daily sheets with lines and discrepancies per
picker; the sheets with one row per outbound delivery are optional). Choose the
same file for both inputs. Parameter: the accuracy target (1.0 = 100%, the default).

### Spot check accuracy (each week)

Upload the week's spot check sheet (the EWM bin list with ONHAND QTY or SOH,
VARIANCE and COMMENT) and, to compare, last week's sheet and the bin list with
the responsible person of each bin. Run "Spot check accuracy" with the day of
the check. The comment decides two things, both editable on the run form:
variances explained by the comment (picked, served, delivered, bin to bin,
moved, corrected) are left out of the "true" accuracy, and comments about a
wrong batch, lot, expiry date or description are listed as data-integrity
flags.

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

