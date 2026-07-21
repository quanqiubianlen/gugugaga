# Desktop Agent

A desktop AI agent application with a chat-style interface, floating button, system tray, multi-conversation management, SSE streaming, and global hotkeys.

## Features

- Chat window with message bubbles and Markdown + code-highlight rendering
- SSE streaming with real-time token display and typing cursor animation
- Multi-conversation management (create, switch, delete, export)
- Draggable floating icon with badge and right-click menu
- System tray with status indicators (idle / working / error) and notifications
- Global hotkeys (toggle window, quick input, voice input)
- Cross-platform hotkey normalisation (Windows / macOS / Linux)
- Settings dialog with hot-reload support
- Auto-start with Windows (registry-based)

## Requirements

- Python 3.10+

## Setup

```bash
pip install -r requirements.txt
```

Edit `config.yaml` to set your API key.

## Usage

```bash
python src/main.py
```

Or run as a module:

```bash
python -m src.main
```

## Packaging

Build a standalone executable with PyInstaller:

**Windows:**
```bash
build.bat
```

**macOS / Linux:**
```bash
chmod +x build.sh
./build.sh
```

### Outputs

| Platform | Portable | Installer |
|---|---|---|
| Windows | `dist/DesktopAgent/` | `dist/DesktopAgent_Setup_0.1.0.exe` (requires Inno Setup) |
| macOS | `dist/DesktopAgent/` | `dist/DesktopAgent_0.1.0.dmg` |
| Linux | `dist/DesktopAgent/` | -- |

### Installer (Windows)

The installer is built with [Inno Setup](https://jrsoftware.org/isinfo.php). It includes:

- Start Menu shortcuts
- Optional desktop icon
- Optional auto-start with Windows
- VC++ Redistributable detection and guidance
- Uninstall support

To generate the installer, install Inno Setup and run `build.bat` (it auto-detects `iscc`).

### Portable mode

The `dist/DesktopAgent/` folder is fully self-contained -- copy it anywhere and run `DesktopAgent.exe`. No installation required.

## Configuration

All settings live in `config.yaml`:

- `api.base_url` -- API endpoint
- `api.api_key` -- Your API key
- `ui.theme` -- Theme: `dark`, `light`, or `system`
- `ui.floating` -- Floating icon settings (enabled, size, opacity, position)
- `features.hotkeys` -- Global hotkey bindings
- `features.autostart` -- Start with Windows
- `features.conversation_history` -- Save conversation history

## Project Structure

```
src/
  main.py              Entry point
  agent/
    api_client.py      API client with retry & error categories
    agent_handler.py   Conversation manager & handler
  ui/
    window.py          Chat window with streaming & bubbles
    floating.py        Floating overlay icon
    tray.py            System tray with status icons
    settings.py        Settings dialog (3 tabs)
  utils/
    config.py          YAML config with hot-reload
    logger.py          Logging setup
    hotkey.py          Cross-platform hotkey manager
    autostart.py       Windows auto-start registry helper
  assets/
    icon.png           Application icon
    icon.ico           Windows icon (generated at build time)
pyinstaller.spec       PyInstaller build configuration
build.bat / build.sh   Build scripts
installer.iss          Inno Setup installer script
```
