# Runtime setup

Use Python 3.10 or newer. Search, scan, show, and image downloads use the standard
library. Contact sheets also require Pillow, declared in the package's
`requirements.txt`.

## Select Python

Check the interpreter before creating an environment:

```sh
python3 --version
python3 -c "from PIL import Image, ImageDraw, ImageOps; print('Contact sheets ready')"
```

If both commands succeed, use that interpreter. Otherwise, check for an existing
environment at `~/.local/share/met-art-research/venv` and reuse it if its Python
version and Pillow import are suitable.

## Install the dependency

For macOS or Linux, create a dedicated environment if needed:

```sh
python3 -m venv ~/.local/share/met-art-research/venv
~/.local/share/met-art-research/venv/bin/python -m pip install -r /absolute/path/to/met-art-research/requirements.txt
~/.local/share/met-art-research/venv/bin/python -c "from PIL import Image, ImageDraw, ImageOps; print('Contact sheets ready')"
```

Resolve the package root from the installed skill: it is two directories above
the directory containing `SKILL.md`. Replace the requirements path with that
absolute path and quote it if it contains spaces. On Windows, use a suitable
user-local environment directory and its `Scripts/python.exe` interpreter.

Use the selected interpreter for subsequent commands. For example:

```sh
~/.local/share/met-art-research/venv/bin/python /absolute/path/to/met-art-research/skills/met-art-research/scripts/met.py contact-sheet 436535 45734
```

Keep environments outside the installed plugin directory so updates preserve
them. If dependency installation fails, report the error; individual image
downloads remain available through the standard-library commands.
