"""Entry point for the dashboard:

    streamlit run run_dashboard.py

A thin launcher, not the app itself. `streamlit run` executes its target
file as a top-level script, which would break aliexpress_dashboard/dashboard/
app.py's package-relative imports if it lived here directly. Importing
app.main() as a proper submodule instead keeps app.py's imports normal.
"""

from aliexpress_dashboard.dashboard.app import main

main()
