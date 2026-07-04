# img-to-ASCII-converter
img2ascii  Turn any image into colored ASCII art — right in your terminal, or exported as HTML, ANSI, or plain text.

# img2ascii

Turn any image into colored ASCII art — right in your terminal, or exported as HTML, ANSI, or plain text.



!ASCII art example


<img width="857" height="610" alt="Screenshot 2026-07-04 234450" src="https://github.com/user-attachments/assets/b5ce3b32-d020-4ba5-90fa-c416b604fe2e" />


## Features

- 🖼️ Works with PNG, JPG, JPEG, BMP, GIF, and anything else Pillow can open
- 🎨 True-color ANSI output in the terminal
- 🧼 Proper alpha compositing — transparent PNGs no longer render as garbage background noise
- 📈 Automatic contrast stretching so flat-color and cartoon/sticker-style images use the full ASCII ramp instead of collapsing into a few symbols
- 💾 Export to `.html` (colored, browser-viewable), `.ansi` (colored terminal text), or `.txt` (plain ASCII)
- 📐 Size by row count or column width, with automatic terminal character aspect correction
- 🔵 Optional dot-only mode for colorful images where shading matters less than color
- 🧠 Interactive mode recommends row count and dot-mode based on the image itself
- 🎛️ Custom ASCII ramps, invertible brightness mapping, adjustable aspect correction
- 🛡️ Overwrite protection on existing output files

## Requirements

- Python 3
- [Pillow](https://python-pillow.org/)
- [NumPy](https://numpy.org/)

```bash
pip install pillow numpy
```

## Usage

### Interactive mode

Just run the script with no arguments and follow the prompts:

```bash
python3 main.py
```

You'll be asked for an image path, size, output file, and whether to use dot mode — with smart defaults recommended based on the image itself.

### Command-line mode

```bash
python3 main.py image.png --rows 60 --output ascii_output.html
```

**Full example with all the extras:**

```bash
python3 main.py cartoon.png \
  --rows 80 \
  --bg-color white \
  --output result.html \
  --force
```

## Options

| Flag | Description |
| --- | --- |
| `image` | Optional image path. If omitted, interactive mode starts. |
| `--rows N` | Target ASCII art height in rows. |
| `--width N` | Target ASCII art width in columns. |
| `--output PATH` | Output file. Defaults to `ascii_output.html`. Format is inferred from the extension (`.html`/`.htm`, `.ansi`/`.ans`, or plain text). |
| `--invert` / `--no-invert` | Toggle inverted brightness mapping for dark terminal backgrounds. Inverted is the default. |
| `--dots` | Use only dot characters — good for colorful images where color matters more than shading. |
| `--ramp TEXT` | Custom characters, ordered darkest to brightest. |
| `--bg-color black\|white` | Background color to composite transparent images onto. Defaults to `black`. |
| `--no-contrast-stretch` | Disable automatic brightness contrast stretching. |
| `--aspect-correction N` | Terminal character aspect correction. Defaults to `0.5`. |
| `--force` | Overwrite the output file if it already exists. |

`--rows` and `--width` are mutually exclusive.

## How it works

1. **Load & composite** — the image is opened with Pillow. If it has transparency, it's alpha-composited onto a solid background (`--bg-color`) instead of just dropping the alpha channel, which used to leave garbage colors behind in "transparent" areas.
2. **Resize** — the image is resized to the target rows/columns using Lanczos resampling, with a correction factor applied so the output doesn't look squashed or stretched in a monospace terminal.
3. **Brightness** — each pixel's brightness is computed with the standard luminance formula (`0.299R + 0.587G + 0.114B`), then contrast-stretched so low-contrast source images still use the full range of ASCII characters.
4. **Character mapping** — brightness values are mapped onto an ASCII ramp (`@%#*+=-:. ` by default, or a custom one via `--ramp`).
5. **Background cleanup** — cells that came from transparent or flat background regions are converted to lightweight characters so backgrounds render as clean space, not dense symbol noise.
6. **Render** — output is printed as true-color ANSI in the terminal, and saved as HTML, ANSI text, or plain text depending on the output file extension.

## Example

Converting a transparent PNG cartoon image at 60 rows:

```bash
python3 main.py peashooter.png --rows 60 --bg-color black --output result.html
```

Produces a clean, colored ASCII silhouette with the background rendered as empty space instead of solid `@` characters — a bug that existed in earlier versions before proper alpha compositing was added.

## Roadmap

- [ ] Automated tests for sizing, brightness mapping, and format selection
- [ ] `--preview-only` flag to print without saving
- [ ] `--no-color` flag for plain terminal output
- [ ] Sample images and example outputs included in the repo
- [ ] `requirements.txt` for easier setup

## License

MIT
