# Clanki

Clanki is a terminal-based Anki review client. lets you review your Anki flashcards directly from the terminal. It uses the same underlying database and scheduling as Anki Desktop, so your progress stays perfectly in sync.

## Features

- Full TUI (Terminal User Interface) for deck selection and review
- Supports all Anki scheduling algorithms
- Image rendering and audio playback support


## Prerequisites

- Python 3.10 or later
- Anki Desktop installed with at least one synced profile
- Anki Desktop must be **closed** when running clanki (database lock)

## Installation

### Using uv (Recommended)

[uv](https://docs.astral.sh/uv/) is the fastest way to install Python tools.

```bash
git clone https://github.com/aaalvn/clanki.git
cd clanki
uv tool install .
```

This installs `clanki` as a global command - no venv activation needed.

### Using pipx

```bash
git clone https://github.com/aaalvn/clanki.git
cd clanki
pipx install .
```

### Using pip (with venv)

```bash
git clone https://github.com/aaalvn/clanki.git
cd clanki
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install .
```

## Setup

### Initial Sync (Required)

Before using clanki, you must sync your Anki collection at least once using Anki Desktop. This ensures your collection database exists and authentication credentials are cached.

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

The TUI provides:
- Profile selection (if you have multiple profiles)
- Deck browser with due counts
- Card review with keyboard navigation


### Sync with AnkiWeb

```bash
clanki sync
```

## Troubleshooting

### "Collection is locked" / "Anki already open, or media currently syncing"

**Cause:** We cannot run both clanki and Anki Desktop at the same time as we lock the collection database to prevent the two from getting out of sync.

**Solution:** Close Anki Desktop completely before running clanki

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

### Profile Selection

Profile selection is handled through the TUI. When you have multiple profiles, clanki will show a profile picker on startup. The most recently used profile is selected by default.

## Development

```bash
cd clanki
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

pytest                 # Run tests
mypy src/clanki        # Type checking
ruff check .           # Linting
```
