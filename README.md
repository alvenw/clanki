<video src="clanki.mp4" controls width="100%"></video>

# Clanki

Clanki is a terminal-based Anki review client that lets you review your Anki flashcards directly from the terminal. It uses the same underlying database and scheduling as Anki Desktop, so your progress stays perfectly in sync.

<video src="clanki-demo.mp4" controls width="100%"></video>

## Features

| Feature | Supported |
|---------|-----------|
| Anki scheduling algorithms | ✅ |
| Image rendering | ✅ |
| Audio playback | ✅ (macOS only) |
| Basic cards | ✅ |
| Cloze cards | ✅ |
| Type in the answer | 🚧 (planned)|
| Image occlusion | ❌ |
| Custom card styling | ❌ |


## Prerequisites

- Python 3.10 or later
- Anki Desktop installed with at least one synced profile
- Anki Desktop must be **closed** when running clanki

## Installation

### Using uv (Recommended)

[uv](https://docs.astral.sh/uv/) is the fastest way to install Python tools.

```bash
uv tool install clanki
```

This installs `clanki` as a global command - no venv activation needed.

### Using pipx

```bash
pipx install clanki
```

### Using pip (with venv)

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install clanki
```

## Setup

### Initial Sync (Required)

Before using clanki, you must sync your Anki collection at least once using Anki Desktop. This ensures your collection database exists and authentication credentials are cached.

If you already have Anki Desktop installed and synced with your AnkiWeb account, you can skip these steps.

1. Open Anki Desktop
2. Sign in to your AnkiWeb account
3. Sync your collection (Sync button or press Y)
4. Close Anki Desktop

### Verify Installation

```bash
# Check version
clanki --version

# Or run as a module
python -m clanki --version
```

## Usage

Simply run `clanki` to launch the TUI:

```bash
clanki
```


### Sync with AnkiWeb

Clanki writes directly to your local Anki database. Syncing is **not automatic**, run this command to push your progress to AnkiWeb:

```bash
clanki sync
```

Sync after reviewing, or before starting if you've reviewed on another device. You can also sync as you would normally through the Anki Desktop app.

## Troubleshooting  

### "No Anki profiles found"

**Cause:** Clanki cannot find your Anki data directory or no profiles exist.

**Solutions:**
1. Ensure Anki Desktop has been installed and run at least once
2. Sync your collection in Anki Desktop at least once
3. Check that profiles exist in your Anki data directory:
   - **macOS:** `~/Library/Application Support/Anki2/`
   - **Linux:** `~/.local/share/Anki2/` (or `$XDG_DATA_HOME/Anki2/`)
   - **Windows:** `%APPDATA%/Anki2/`

### "Collection not found for profile"

**Cause:** The profile directory exists but doesn't contain a collection database.

**Solution:** Open Anki Desktop, select the profile, and sync to create the collection.

### Sync fails with "No sync credentials found"

**Cause:** AnkiWeb credentials are not cached locally.

**Solution:** Open Anki Desktop, sign in to AnkiWeb, and sync at least once. This caches your credentials for clanki to use.

## Advanced Configuration

### Custom Anki Data Directory

If your Anki data is stored in a non-standard location, set the `ANKI_BASE` environment variable:

```bash
export ANKI_BASE="/path/to/custom/Anki2"
clanki
```

This is useful for:
- Portable Anki installations
- Multiple Anki installations
- Testing with a separate data directory

## Roadmap

### Planned

- [ ] More review actions (bury, suspend, flag, etc.)
- [ ] Custom decks (filtered decks)
- [ ] Support for type in answer cards
- [ ] Profile switching within the TUI
- [ ] Review statistics
- [ ] Ability to run program with Anki desktop app open

### Not Currently Planned

- Ability to create or edit cards/decks
- Rendering custom card styles
- Plugin support
- Math/LaTeX rendering
