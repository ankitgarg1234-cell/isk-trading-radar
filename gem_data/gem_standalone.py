"""Isolated Render entrypoint: GEM V1 has been replaced by Tier-1 V3.

This compatibility path is retained because the Render start command still imports
`gem_data.gem_standalone:app`. No old GEM routes, research workers, databases,
Marketstack clients, or trading executors are imported or started here.
"""
from tier1_v3.dashboard import app
