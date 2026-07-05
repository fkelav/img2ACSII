from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import numpy as np
except ImportError:
    np = None


ASCII_RAMP = "@%#*+=-:. "
DEFAULT_OUTPUT_FILE = "ascii_output.html"
DEFAULT_ROWS = 80
DEFAULT_TARGET_COLUMNS = 120
DETAIL_SAMPLE_SIZE = 160
DETAIL_SCORE_THRESHOLD = 24
# Most monospace terminal fonts render characters roughly twice as tall as
# they are wide. Without this correction, ASCII output looks vertically stretched.
CHAR_ASPECT_CORRECTION = 0.5
ANSI_RESET = "\033[0m"
ANSI_RE = re.compile(r"\033\[[0-9;]*m")
BACKGROUND_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
}
BACKGROUND_MODES = ("spaces", *BACKGROUND_COLORS)
BACKGROUND_CHAR = "."


def ask_image_path() -> Path:
    while True:
        raw_path = input("Image path: ").strip().strip('"')
        image_path = Path(raw_path).expanduser()

        if image_path.is_file():
            return image_path

        print("That image path was not found. Please try again.")


def ask_rows(recommended_rows: int | None = None) -> int:
    prompt = "How many rows should the ASCII art have?"
    if recommended_rows is not None:
        prompt += f" [{recommended_rows}]"
    prompt += " "

    while True:
        raw_rows = input(prompt).strip()

        if not raw_rows and recommended_rows is not None:
            return recommended_rows

        try:
            rows = int(raw_rows)
        except ValueError:
            print("Please enter a whole number greater than 0.")
            continue

        if rows > 0:
            return rows

        print("Please enter a number greater than 0.")


def ask_width() -> int | None:
    while True:
        raw_width = input("How many columns should the ASCII art have? [use rows] ").strip()

        if not raw_width:
            return None

        try:
            width = int(raw_width)
        except ValueError:
            print("Please enter a whole number greater than 0.")
            continue

        if width > 0:
            return width

        print("Please enter a number greater than 0.")


def ask_output_file() -> Path:
    raw_output = input(f"Output HTML file [{DEFAULT_OUTPUT_FILE}]: ").strip().strip('"')
    return normalize_output_path(Path(raw_output or DEFAULT_OUTPUT_FILE).expanduser())


def ask_background_color(default: str = "spaces") -> tuple[int, int, int] | None:
    choices = "/".join(BACKGROUND_MODES)
    while True:
        raw_mode = input(f"Background characters ({choices}) [{default}]: ").strip().lower()
        mode = raw_mode or default

        if mode == "spaces":
            print("Using spaces for background pixels.")
            return None
        if mode in BACKGROUND_COLORS:
            print(f"Using {mode} characters for background pixels.")
            return BACKGROUND_COLORS[mode]

        print(f"Please choose one of: {choices}.")


def normalize_output_path(output_path: Path) -> Path:
    return output_path.with_suffix(".html") if not output_path.suffix else output_path


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "

    while True:
        answer = input(prompt + suffix).strip().lower()

        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False

        print("Please answer yes or no.")


def ask_after_generation_action() -> str:
    print()
    print("What would you like to do next?")
    print("1. Make another image")
    print("2. Exit")

    while True:
        answer = input("Choose 1 or 2: ").strip().lower()

        if answer in {"1", "another", "again", "a"}:
            return "again"
        if answer in {"2", "exit", "quit", "q"}:
            return "exit"

        print("Please choose 1 to make another image or 2 to exit.")


def brightness_to_char(brightness: int, ramp: str = ASCII_RAMP, invert: bool = False) -> str:
    if not ramp:
        raise ValueError("ASCII ramp must not be empty.")

    if invert:
        brightness = 255 - brightness

    index = brightness * (len(ramp) - 1) // 255
    return ramp[index]


def load_rgb_image(image_path: Path, background: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    with Image.open(image_path) as image:
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image = image.convert("RGBA")
            backdrop = Image.new("RGBA", image.size, (*background, 255))
            image = Image.alpha_composite(backdrop, image)
        return image.convert("RGB")


def load_rgb_image_with_alpha(
    image_path: Path,
    background: tuple[int, int, int] = (0, 0, 0),
) -> tuple[Image.Image, Image.Image | None]:
    with Image.open(image_path) as image:
        has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
        if not has_alpha:
            return image.convert("RGB"), None

        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        backdrop = Image.new("RGBA", rgba.size, (*background, 255))
        composited = Image.alpha_composite(backdrop, rgba)
        return composited.convert("RGB"), alpha


def recommend_rows_for_image(
    image_size: tuple[int, int],
    target_columns: int = DEFAULT_TARGET_COLUMNS,
    aspect_correction: float = CHAR_ASPECT_CORRECTION,
) -> int:
    if target_columns <= 0:
        raise ValueError("Target columns must be greater than 0.")
    if aspect_correction <= 0:
        raise ValueError("Aspect correction must be greater than 0.")

    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be greater than 0.")

    aspect_ratio = image_width / image_height
    return max(1, round(target_columns * aspect_correction / aspect_ratio))


def recommend_dots_for_image(image: Image.Image) -> tuple[bool, str]:
    sample = image.convert("RGB").copy()
    sample.thumbnail((DETAIL_SAMPLE_SIZE, DETAIL_SAMPLE_SIZE), Image.Resampling.LANCZOS)

    brightness = compute_brightness(sample)
    vertical_edges = np.abs(np.diff(brightness.astype(np.int16), axis=0))
    horizontal_edges = np.abs(np.diff(brightness.astype(np.int16), axis=1))
    edge_score = (vertical_edges.mean() + horizontal_edges.mean()) / 2
    contrast_score = brightness.std()
    detail_score = (contrast_score * 0.7) + (edge_score * 1.8)

    pixels = np.asarray(sample, dtype=np.float64)
    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    colorfulness = np.std(red - green) + (0.3 * np.std((red + green) / 2 - blue))

    if colorfulness >= 35 and edge_score < 18:
        return True, "dots keep colorful, smooth areas cleaner"
    if detail_score >= DETAIL_SCORE_THRESHOLD:
        return False, "full characters keep the image's light/dark detail clearer"
    if colorfulness >= 35:
        return True, "dots keep the color changes cleaner than mixed symbols"
    return False, "full characters add useful shading to this image"


def describe_image_recommendations(image_path: Path) -> tuple[int | None, bool]:
    try:
        with Image.open(image_path) as image:
            image_size = image.size
            use_dots, dots_reason = recommend_dots_for_image(image)
    except OSError as error:
        print(f"Could not inspect that image: {error}")
        return None, False

    recommended_rows = recommend_rows_for_image(image_size)
    recommended_columns = round(recommended_rows * (image_size[0] / image_size[1]) / CHAR_ASPECT_CORRECTION)
    print()
    print(f"Image size: {image_size[0]} x {image_size[1]} pixels")
    print(f"Recommended rows: {recommended_rows} (about {recommended_columns} columns)")
    if use_dots:
        print(f"Recommended characters: dots only, because {dots_reason}.")
    else:
        print(f"Recommended characters: full character ramp, because {dots_reason}.")
    return recommended_rows, use_dots


def resize_for_ascii(
    image: Image.Image,
    rows: int | None = None,
    width: int | None = None,
    aspect_correction: float = CHAR_ASPECT_CORRECTION,
) -> Image.Image:
    if rows is None and width is None:
        raise ValueError("Either rows or width must be provided.")
    if rows is not None and rows <= 0:
        raise ValueError("Rows must be greater than 0.")
    if width is not None and width <= 0:
        raise ValueError("Width must be greater than 0.")
    if aspect_correction <= 0:
        raise ValueError("Aspect correction must be greater than 0.")

    image_width, image_height = image.size
    aspect_ratio = image_width / image_height

    if rows is not None:
        columns = max(1, round(rows * aspect_ratio / aspect_correction))
        return image.resize((columns, rows), Image.Resampling.LANCZOS)

    assert width is not None
    computed_rows = max(1, round(width * aspect_correction / aspect_ratio))
    return image.resize((width, computed_rows), Image.Resampling.LANCZOS)


def compute_brightness(image: Image.Image) -> np.ndarray:
    if np is None:
        raise RuntimeError("NumPy is required to compute image brightness.")

    pixels = np.asarray(image, dtype=np.float64)
    brightness = 0.299 * pixels[..., 0] + 0.587 * pixels[..., 1] + 0.114 * pixels[..., 2]
    return brightness.round().astype(np.uint8)


def normalize_contrast(brightness: np.ndarray) -> np.ndarray:
    low, high = brightness.min(), brightness.max()
    if high == low:
        return brightness

    stretched = (brightness.astype(np.float64) - low) * 255 / (high - low)
    return stretched.round().astype(np.uint8)


def brightness_array_to_chars(
    brightness: np.ndarray,
    ramp: str = ASCII_RAMP,
    invert: bool = False,
) -> np.ndarray:
    if not ramp:
        raise ValueError("ASCII ramp must not be empty.")

    values = 255 - brightness if invert else brightness
    indexes = values.astype(np.uint16) * (len(ramp) - 1) // 255
    ramp_array = np.asarray(list(ramp))
    return ramp_array[indexes]


def dots_array(shape: tuple[int, int]) -> np.ndarray:
    return np.full(shape, ".", dtype="<U1")


def transparent_background_mask(
    alpha_mask: Image.Image | None,
    transparency_threshold: int = 8,
) -> np.ndarray:
    if alpha_mask is None:
        return np.zeros((0, 0), dtype=bool)

    return np.asarray(alpha_mask, dtype=np.uint8) <= transparency_threshold


def edge_background_mask(
    resized_image: Image.Image,
    color_threshold: int = 16,
) -> np.ndarray:
    pixels = np.asarray(resized_image, dtype=np.int16)
    height, width = pixels.shape[:2]
    corner_colors = np.array(
        [
            pixels[0, 0],
            pixels[0, width - 1],
            pixels[height - 1, 0],
            pixels[height - 1, width - 1],
        ],
        dtype=np.int16,
    )

    background_pixels = np.zeros((height, width), dtype=bool)
    for corner_color in corner_colors:
        background_pixels |= np.abs(pixels - corner_color).max(axis=2) <= color_threshold
    return background_pixels


def apply_background_chars(
    chars: np.ndarray,
    background_pixels: np.ndarray,
    background_char: str = BACKGROUND_CHAR,
) -> np.ndarray:
    if not background_pixels.any():
        return chars

    result = chars.copy()
    result[background_pixels] = background_char
    return result


def render_color_lines(
    resized_image: Image.Image,
    chars: np.ndarray,
    background_color: tuple[int, int, int] | None = None,
    background_pixels: np.ndarray | None = None,
) -> list[str]:
    pixels = np.asarray(resized_image, dtype=np.uint8)
    terminal_background = background_color or (0, 0, 0)
    bg_red, bg_green, bg_blue = terminal_background
    if background_pixels is None:
        background_pixels = np.zeros(chars.shape, dtype=bool)
    lines = []

    for pixel_row, char_row, background_row in zip(pixels, chars, background_pixels):
        line = []
        for (red, green, blue), char, is_background in zip(pixel_row, char_row, background_row):
            if is_background and background_color is not None:
                red, green, blue = background_color
            line.append(f"\033[38;2;{red};{green};{blue};48;2;{bg_red};{bg_green};{bg_blue}m{char}")
        lines.append("".join(line) + ANSI_RESET)

    return lines


def render_plain_lines(chars: np.ndarray) -> list[str]:
    return ["".join(row.tolist()) for row in chars]


def render_html(
    resized_image: Image.Image,
    chars: np.ndarray,
    background_color: tuple[int, int, int] | None = None,
    background_pixels: np.ndarray | None = None,
) -> str:
    pixels = np.asarray(resized_image, dtype=np.uint8)
    if background_pixels is None:
        background_pixels = np.zeros(chars.shape, dtype=bool)
    lines = []

    for pixel_row, char_row, background_row in zip(pixels, chars, background_pixels):
        line = []
        for (red, green, blue), char, is_background in zip(pixel_row, char_row, background_row):
            if is_background and background_color is not None:
                red, green, blue = background_color
            escaped_char = html.escape(str(char))
            line.append(f'<span style="color: rgb({red}, {green}, {blue})">{escaped_char}</span>')
        lines.append("".join(line))

    body = "\n".join(lines)
    page_background = background_color or (0, 0, 0)
    background_css = f"rgb({page_background[0]}, {page_background[1]}, {page_background[2]})"
    text_css = "#f4f4f4" if sum(page_background) < 384 else "#111111"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ASCII Art</title>
<style>
body {{
    margin: 0;
    background: {background_css};
    color: {text_css};
    overflow: auto;
}}
pre {{
    margin: 16px;
    display: inline-block;
    font-family: Consolas, "Courier New", monospace;
    font-size: 8px;
    line-height: 1;
    letter-spacing: 0;
    white-space: pre;
}}
span {{
    font: inherit;
}}
</style>
</head>
<body>
<pre>{body}</pre>
</body>
</html>
"""


def convert_image_to_ascii(
    image_path: Path,
    rows: int | None = None,
    width: int | None = None,
    ramp: str = ASCII_RAMP,
    invert: bool = False,
    aspect_correction: float = CHAR_ASPECT_CORRECTION,
    dots: bool = False,
    background_color: tuple[int, int, int] | None = None,
    contrast_stretch: bool = True,
) -> tuple[str, str, str]:
    composite_background = background_color or (0, 0, 0)
    image, alpha_mask = load_rgb_image_with_alpha(image_path, background=composite_background)
    resized = resize_for_ascii(
        image,
        rows=rows,
        width=width,
        aspect_correction=aspect_correction,
    )
    resized_alpha = None
    if alpha_mask is not None:
        resized_alpha = resize_for_ascii(
            alpha_mask,
            rows=rows,
            width=width,
            aspect_correction=aspect_correction,
        )

    brightness = compute_brightness(resized)
    if contrast_stretch:
        brightness = normalize_contrast(brightness)
    chars = dots_array(brightness.shape) if dots else brightness_array_to_chars(
        brightness,
        ramp=ramp,
        invert=invert,
    )
    background_pixels = edge_background_mask(resized)
    transparent_pixels = transparent_background_mask(resized_alpha)
    if transparent_pixels.shape == background_pixels.shape:
        background_pixels = background_pixels | transparent_pixels

    background_char = BACKGROUND_CHAR if background_color is not None else " "
    chars = apply_background_chars(chars, background_pixels, background_char=background_char)
    color_lines = render_color_lines(
        resized,
        chars,
        background_color=background_color,
        background_pixels=background_pixels,
    )
    plain_lines = render_plain_lines(chars)
    html_art = render_html(
        resized,
        chars,
        background_color=background_color,
        background_pixels=background_pixels,
    )

    return "\n".join(color_lines), "\n".join(plain_lines), html_art


def save_ascii(output_path: Path, color_ascii: str, plain_ascii: str, html_art: str, force: bool = False) -> str:
    if output_path.exists() and not force:
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = output_path.suffix.lower()
    if suffix in {".ansi", ".ans"}:
        output_path.write_text(color_ascii, encoding="utf-8")
        return "ANSI-colored ASCII art"
    if suffix in {".html", ".htm"}:
        output_path.write_text(html_art, encoding="utf-8")
        return "HTML-colored ASCII art"

    output_path.write_text(ANSI_RE.sub("", plain_ascii), encoding="utf-8")
    return "plain ASCII art"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert an image to colored ASCII art.")
    parser.set_defaults(invert=True)
    parser.add_argument("image", nargs="?", type=Path, help="Image file to convert.")
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument(
        "--rows",
        type=int,
        help=f"Target ASCII art height in rows. Default: {DEFAULT_ROWS}",
    )
    size_group.add_argument("--width", type=int, help="Target ASCII art width in columns.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_FILE),
        help=f"Output file. Use .html for browser colors, or .txt for plain text. Default: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--invert",
        dest="invert",
        action="store_true",
        help="Use dark-terminal brightness mapping. This is the default.",
    )
    parser.add_argument(
        "--no-invert",
        dest="invert",
        action="store_false",
        help="Disable the default dark-terminal brightness mapping.",
    )
    parser.add_argument("--dots", action="store_true", help="Use only dot characters for the ASCII image.")
    parser.add_argument("--ramp", default=ASCII_RAMP, help="Characters from darkest to brightest.")
    parser.add_argument(
        "--bg-color",
        choices=BACKGROUND_MODES,
        default="spaces",
        help="Background character mode. Default: spaces.",
    )
    parser.add_argument(
        "--no-contrast-stretch",
        dest="contrast_stretch",
        action="store_false",
        default=True,
        help="Disable automatic contrast stretching. On by default.",
    )
    parser.add_argument(
        "--aspect-correction",
        type=float,
        default=CHAR_ASPECT_CORRECTION,
        help=f"Terminal character aspect correction. Default: {CHAR_ASPECT_CORRECTION}",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite the output file if it exists.")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.rows is not None and args.rows <= 0:
        parser.error("--rows must be greater than 0.")
    if args.width is not None and args.width <= 0:
        parser.error("--width must be greater than 0.")
    if args.aspect_correction <= 0:
        parser.error("--aspect-correction must be greater than 0.")
    if not args.ramp:
        parser.error("--ramp must not be empty.")

    return args


def run_interactive() -> tuple[
    Path,
    int | None,
    int | None,
    Path,
    bool,
    str,
    float,
    bool,
    bool,
    tuple[int, int, int] | None,
    bool,
] | None:
    print("Image to colored ASCII converter")
    print("--------------------------------")

    image_path = ask_image_path()
    recommended_rows, recommended_dots = describe_image_recommendations(image_path)
    width = ask_width()
    rows = None if width is not None else ask_rows(recommended_rows)
    output_path = ask_output_file()
    invert = True
    dots = ask_yes_no("Use only dot characters?", default=recommended_dots)
    background_color = ask_background_color()
    contrast_stretch = ask_yes_no("Stretch contrast automatically?", default=True)
    force = False

    if output_path.exists():
        force = ask_yes_no(f"{output_path} already exists. Overwrite it?", default=False)
        if not force:
            print("Canceled without overwriting the output file.")
            return None

    return (
        image_path,
        rows,
        width,
        output_path,
        invert,
        ASCII_RAMP,
        CHAR_ASPECT_CORRECTION,
        force,
        dots,
        background_color,
        contrast_stretch,
    )


def generate_and_save(
    image_path: Path,
    rows: int | None,
    width: int | None,
    output_path: Path,
    invert: bool,
    ramp: str,
    aspect_correction: float,
    force: bool,
    dots: bool,
    background_color: tuple[int, int, int] | None,
    contrast_stretch: bool,
) -> bool:
    try:
        color_ascii, plain_ascii, html_art = convert_image_to_ascii(
            image_path,
            rows=rows,
            width=width,
            ramp=ramp,
            invert=invert,
            aspect_correction=aspect_correction,
            dots=dots,
            background_color=background_color,
            contrast_stretch=contrast_stretch,
        )
    except OSError as error:
        print(f"Could not open that image: {error}")
        return False
    except ValueError as error:
        print(error)
        return False

    print()
    print(color_ascii)

    try:
        saved_kind = save_ascii(output_path, color_ascii, plain_ascii, html_art, force=force)
    except FileExistsError:
        print()
        print(f"Output file already exists: {output_path}")
        print("Use --force to overwrite it.")
        return False

    print()
    print(f"Saved {saved_kind} to: {output_path.resolve()}")
    return True


def run_interactive_session() -> None:
    while True:
        interactive_values = run_interactive()
        if interactive_values is not None:
            generate_and_save(*interactive_values)

        if ask_after_generation_action() == "exit":
            print("Goodbye.")
            return


def main() -> None:
    args = parse_args(sys.argv[1:])

    if Image is None:
        print("Pillow is required to read and resize images.")
        print("Install it with: pip install pillow")
        return
    if np is None:
        print("NumPy is required to convert images efficiently.")
        print("Install it with: pip install numpy")
        return

    if args.image is None:
        run_interactive_session()
        return
    else:
        image_path = args.image.expanduser()
        width = args.width
        rows = None if width is not None else (args.rows if args.rows is not None else DEFAULT_ROWS)
        output_path = normalize_output_path(args.output.expanduser())
        invert = args.invert
        ramp = args.ramp
        aspect_correction = args.aspect_correction
        force = args.force
        dots = args.dots
        background_color = None if args.bg_color == "spaces" else BACKGROUND_COLORS[args.bg_color]
        contrast_stretch = args.contrast_stretch

        if not image_path.is_file():
            print(f"Image path was not found: {image_path}")
            return

    generate_and_save(
        image_path,
        rows,
        width,
        output_path,
        invert,
        ramp,
        aspect_correction,
        force,
        dots,
        background_color,
        contrast_stretch,
    )


if __name__ == "__main__":
    main()
