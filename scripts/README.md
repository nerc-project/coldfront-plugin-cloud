# Sample Seeding Script for Daily Billable Usage

To run the script to populate the test DB use:

```
python manage.py shell < /mnt/MOC/coldfront-plugin-cloud/scripts/seed_sample_daily_billable_usage_shell.py
```

Configure the `seed_sample_daily_billable_usage_shell.py` file before running the script.

```
# --- configure before running ---
ALLOCATION_ID = 4

# Pick one date mode (set the others to None / False):
SINGLE_DATE = None  # YYYY-MM-DD, or None
MONTH = None  # YYYY-MM, or None
CURRENT_MONTH = True  # seed every day in the current calendar month
THROUGH_TODAY = True # with CURRENT_MONTH, skip future days
```
