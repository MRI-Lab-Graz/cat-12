# Sphinx configuration for Read the Docs

from __future__ import annotations

from datetime import date

project = "CAT12 Standalone Wrapper"
author = "MRI Lab Graz"
copyright = f"{date.today().year}, {author}"

extensions = [
    "myst_parser",
]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]

source_suffix = {
    ".md": "markdown",
}

master_doc = "index"

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "**/.ipynb_checkpoints",
]

html_theme = "sphinx_rtd_theme"

# Read the Docs logo (path is relative to this conf.py file)
html_logo = "cat-bids.png"

# Keep navigation clean and predictable on RTD
html_show_sourcelink = False
html_show_sphinx = False

# If you later add API docs, enable and configure autodoc here.
