# Dine On Campus Menu for Home Assistant

Custom integration to display your campus dining hall menu in Home Assistant, using the [DineOnCampus API](https://apiv4.dineoncampus.com/sites/public).

## Features
- Pick your school, location, and meal period in the UI
- Dynamic mode: shows the current meal based on configurable time windows
- Per-category sensors (e.g. Flame, Grill, Deli) with item counts + item lists
- Refresh button for manual updates
- Auto-refresh every 5 minutes

## Installation
1. Add this repository to HACS (Custom Repository → `https://github.com/quacksire/dineoncampus-ha`)
2. Restart Home Assistant
3. Add the integration via Settings → Devices & Services → Add Integration → **Dine On Campus Menu**

