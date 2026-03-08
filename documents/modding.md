# Creating Extensions for Swift Browser

This guide covers the basics of creating extensions (mods) for Swift Browser.

---

## Requirements

- **Python 3.x** knowledge (basic)
- **PyQt6** familiarity (helpful but not required)
- A text editor

---

## Extension Structure

An extension is a folder containing at minimum a `main.py` file:

```
my_extension/
├── main.py        (required)
├── style.qss      (optional - custom styles)
└── icon.png       (optional - extension icon)
```

---

## The main.py File

Your `main.py` must contain:

### 1. extension_info (Required)

A dictionary with these **required** fields:

```python
extension_info = {
    "name": "My Extension",           # Display name
    "version": "1.0",                 # Version string
    "author": "Your Name",            # Your name/username
    "description": "What it does.",   # Brief description
    "source": "https://github.com/you/repo"  # Source code URL (GPL required)
}
```

> **⚠️ Important:** The `source` field is **required** for GPL compliance. It must link to where users can access your extension's source code.

### 2. on_load Function (Required)

Called when your extension is loaded:

```python
def on_load(browser):
    """Called when the extension loads."""
    # Your code here
    print(f"{extension_info['name']} loaded!")
```

The `browser` object gives you access to:

| Property/Method | Description |
|-----------------|-------------|
| `browser.tabs` | The tab widget |
| `browser.current_web_view()` | Current page's web view |
| `browser.toolbar` | Main toolbar |
| `browser.status_bar` | Status bar |
| `browser.new_tab(url)` | Open a new tab |
| `browser.setStyleSheet(qss)` | Apply custom styles |

### 3. on_unload Function (Required)

Called when your extension is disabled or removed:

```python
def on_unload(browser):
    """Called when the extension unloads."""
    # Clean up your UI elements here
    pass
```

---

## Minimal Example

```python
extension_info = {
    "name": "Hello World",
    "version": "1.0",
    "author": "You",
    "description": "Shows a message when loaded.",
    "source": "https://github.com/yourusername/hello-world"
}

def on_load(browser):
    browser.status_bar.showMessage("Hello from my extension!", 3000)

def on_unload(browser):
    pass
```

---

## Adding Custom Styles (Optional)

Create a `style.qss` file in your extension folder to add custom CSS-like styles:

```css
/* style.qss */
#addressBar {
    border: 2px solid #ff6b6b;
    border-radius: 8px;
}

QTabBar::tab {
    background: #2d2d2d;
    color: white;
}
```

Styles are automatically applied when your extension loads.

---

## Packaging Your Extension

To distribute your extension, package it as a `.zip` file:

1. Select your extension folder (containing `main.py`)
2. Compress it to a `.zip` file
3. Share the `.zip` file

Users can install it via **Extensions Manager → Install from .zip**

```
my_extension.zip
└── my_extension/
    ├── main.py
    ├── style.qss (optional)
    └── icon.ico (optional)
```

---

## Licensing

Swift Browser and its extension system are licensed under **GPL (GNU General Public License)**.

### What This Means For You:

- ✅ You **can** create and distribute extensions freely
- ✅ You **can** modify and share your extensions
- ⚠️ You **must** provide source code access (the `source` field)
- ⚠️ Your extension **must** also be GPL-compatible if distributed

The `source` field in `extension_info` is mandatory—it must link to where users can view your extension's source code (GitHub, GitLab, etc.).

---

## Validation Rules

Your extension will be rejected if:

- ❌ `main.py` is missing
- ❌ `extension_info` is missing or not a dictionary
- ❌ Any required field is missing (`name`, `version`, `author`, `description`, `source`)
- ❌ Any field is empty or not a string
- ❌ The extension name contains invalid characters (use letters, numbers, underscores only)

---

## Tips

- Test your extension locally before packaging
- Use `print()` statements for debugging (check terminal output)
- Clean up any UI elements in `on_unload()` to prevent issues
- Keep your extension lightweight to avoid performance impact

---