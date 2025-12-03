import os
import time
import random
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---

# Main folder is the folder where this script lives (e.g. "Watermark")
ROOT_DIR = Path(__file__).resolve().parent
LOGS_DIR = ROOT_DIR / "Logs"

# Image types to process
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")

# Optional: path to a TTF font file you like
# For example: r"C:\Windows\Fonts\arial.ttf"
FONT_PATH = None  # if None, it will try Arial or fall back to default

TEXT_COLOR = (255, 0, 0)      # R,G,B (red)

MARGIN_RATIO = 0.02           # 2% of image width as margin
FONT_SIZE_RATIO = 0.04        # 4% of image height as font size

# Name of the output folder created next to each "stills" folder
OUTPUT_FOLDER_NAME = "Stills With Pole Number"

# Prefixes to ignore as "not a real pole ID" (case-insensitive)
IGNORED_PREFIXES = {"noasset"}

# Artificial "UI" timing controls (pre-[Y/N] and headings)
TYPE_DELAY = 0.005        # seconds per character for slow printing
SCAN_BUFFER_MIN = 0.15    # min extra delay before each "Scanned stills..." line
SCAN_BUFFER_MAX = 0.45    # max extra delay

# Artificial delays AFTER the user confirms [Y/N]
# Used for pauses around "Starting watermarking..." and between folder batches
POST_CONFIRM_DELAY_MIN = 0.3
POST_CONFIRM_DELAY_MAX = 1.0

# Artificial delay BEFORE each image is actually saved
# (set both to 0.0 if you want no per-image delay)
PER_IMAGE_DELAY_MIN = 0.0
PER_IMAGE_DELAY_MAX = 0.0


# --- SLOW PRINT HELPERS (used before [Y/N] + headings + summary) ---

def slow_print(text="", end="\n", delay=TYPE_DELAY):
    """Print text character by character with a small delay."""
    s = str(text)
    for ch in s:
        print(ch, end="", flush=True)
        if delay > 0:
            time.sleep(delay)
    print(end, end="", flush=True)


def slow_line(char, length):
    """Print a repeated char as a slow line."""
    slow_print(char * length)


# --- WATERMARK HELPERS ---

def get_pole_id(filename):
    """
    Extract pole ID = everything before the first underscore.

    Examples:
        '603504_2025-11-25_xx.jpg'   -> '603504'
        'D825042_2025-11-25_xx.jpg'  -> 'D825042'
        'NoAsset_2025-11-25_xx.jpg' -> ignored (returns None)
    """
    base = os.path.basename(filename)

    # Require an underscore so we don't try to use random names as IDs
    if "_" not in base:
        return None

    first_part = base.split("_", 1)[0]

    # Ignore certain known non-asset prefixes (case-insensitive)
    if first_part.lower() in IGNORED_PREFIXES:
        return None

    # Otherwise, treat the whole prefix as the pole ID text
    return first_part


def load_font(img_height):
    size = max(12, int(img_height * FONT_SIZE_RATIO))
    if FONT_PATH is not None and os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size=size)
    else:
        # Try Arial, then fallback to default
        try:
            return ImageFont.truetype("arial.ttf", size=size)
        except Exception:
            return ImageFont.load_default()


def watermark_image(path_in, path_out):
    """
    Watermark a single image.
    Returns True if written, False if skipped (e.g. no usable pole ID).
    """
    pole_id = get_pole_id(path_in.name)
    if pole_id is None:
        print(f"    Skipping {path_in.name}: no usable pole ID found.")
        return False

    with Image.open(path_in) as im:
        im = im.convert("RGB")
        draw = ImageDraw.Draw(im)

        font = load_font(im.height)
        text = pole_id

        # Text size and position (top-right) using textbbox (Pillow 10+)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        margin = int(im.width * MARGIN_RATIO)
        x = im.width - text_w - margin
        y = margin

        # Main red text (no outline)
        draw.text((x, y), text, font=font, fill=TEXT_COLOR)

        # Honor per-image delay BEFORE saving & printing
        if PER_IMAGE_DELAY_MAX > 0:
            delay = random.uniform(PER_IMAGE_DELAY_MIN, PER_IMAGE_DELAY_MAX)
            time.sleep(max(0.0, delay))

        path_out.parent.mkdir(parents=True, exist_ok=True)
        im.save(path_out, quality=95)
        print(f"    Saved {path_out.name}")
        return True


def find_stills_folders(root):
    """Yield all folders named 'stills' (case-insensitive) under root."""
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d.lower() == "stills":
                yield Path(dirpath) / d


def build_header_line(idx, total, stills_dir):
    """
    Build the progress header line for a given stills folder.

    Example format:
        [i/n] 'Balclutha\\...\\stills' -> 'Stills With Pole Number'
    """
    rel_to_root = stills_dir.relative_to(ROOT_DIR)
    if rel_to_root.parts:
        job_root_abs = ROOT_DIR / rel_to_root.parts[0]
    else:
        job_root_abs = ROOT_DIR

    rel_parent = stills_dir.parent.relative_to(job_root_abs)
    job_rel = job_root_abs.relative_to(ROOT_DIR)
    output_dir = stills_dir.parent / OUTPUT_FOLDER_NAME

    return (
        f"[{idx}/{total}] "
        f"'{job_rel}\\{rel_parent}\\{stills_dir.name}' -> '{output_dir.name}'"
    )


def write_log(job_stats, job_stills, folder_stats,
              total_images, total_processed, conversion_time):
    """
    Write a log file into ROOT_DIR/Logs.
    The log name is based on the job folder if there is only one.
    Returns the Path to the log file.
    """
    LOGS_DIR.mkdir(exist_ok=True)

    jobs_sorted = sorted(job_stats.keys(), key=lambda p: str(p))
    now = datetime.now()

    if len(jobs_sorted) == 1:
        job_name = jobs_sorted[0].name
        log_filename = f"{job_name} - Log.txt"
    else:
        log_filename = f"Watermark Log - {now:%Y-%m-%d_%H-%M-%S}.txt"

    log_path = LOGS_DIR / log_filename

    total_skipped = sum(stats["skipped"] for stats in folder_stats.values())

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("Watermark Log\n")
        f.write("=============\n")
        f.write(f"Run time : {now:%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Root folder : {ROOT_DIR}\n\n")

        f.write("Summary\n")
        f.write("-------\n")
        f.write(f"Total 'stills' folders with images: {len(folder_stats)}\n")
        f.write(f"Total images found: {total_images}\n")
        f.write(f"Total watermarked: {total_processed}\n")
        f.write(f"Total skipped: {total_skipped}\n")
        f.write(
            f"Conversion time (seconds, excluding pauses): {conversion_time:.2f}\n\n"
        )

        f.write("Per-folder details\n")
        f.write("------------------\n")

        idx = 1
        for job_root_abs in jobs_sorted:
            for stills_dir in sorted(job_stills[job_root_abs], key=lambda p: str(p)):
                if stills_dir not in folder_stats:
                    continue
                stats = folder_stats[stills_dir]
                rel_path = stills_dir.relative_to(ROOT_DIR)

                f.write(f"[{idx}] {rel_path}\n")
                f.write(f"    Images found : {stats['found']}\n")
                f.write(f"    Watermarked  : {stats['watermarked']}\n")
                f.write(f"    Skipped      : {stats['skipped']}\n")

                if stats["skipped_files"]:
                    f.write("    Skipped files:\n")
                    for name in stats["skipped_files"]:
                        f.write(f"        {name}\n")

                f.write("\n")
                idx += 1

    return log_path


# --- MAIN LOGIC ---

def main():
    # Header
    slow_print(f"Main folder: '{ROOT_DIR.name}'")
    full_path_line = f"Full path : {ROOT_DIR}"
    slow_print(full_path_line)
    slow_line("-", len(full_path_line))
    slow_print()  # blank line

    # Find all 'stills' folders anywhere under ROOT_DIR
    stills_dirs = list(find_stills_folders(ROOT_DIR))
    if not stills_dirs:
        slow_print("No 'stills' folders found under this directory.")
        return

    # Stats grouped by top-level job folder (e.g. 'BALCLUTHA 25-11-25')
    job_stills = defaultdict(list)   # job_root_abs -> [stills_dir]
    per_stills_images = {}           # stills_dir -> [image_paths]
    job_stats = {}                   # job_root_abs -> {"stills": int, "images": int}
    folder_stats = {}                # stills_dir -> dict with found/watermarked/skipped

    total_images = 0

    # Scan each stills folder for images (but don't watermark yet)
    for stills_dir in sorted(stills_dirs, key=lambda p: str(p)):
        rel_to_root = stills_dir.relative_to(ROOT_DIR)

        # Top-level folder under ROOT_DIR (job folder)
        if rel_to_root.parts:
            job_root_abs = ROOT_DIR / rel_to_root.parts[0]
        else:
            job_root_abs = ROOT_DIR

        # All image files in this stills dir
        image_files = [
            f for f in stills_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]
        per_stills_images[stills_dir] = image_files

        count = len(image_files)
        total_images += count

        # Only track stats if there is at least one image
        if count > 0:
            job_stills[job_root_abs].append(stills_dir)
            stats = job_stats.setdefault(job_root_abs, {"stills": 0, "images": 0})
            stats["stills"] += 1
            stats["images"] += count

            folder_stats[stills_dir] = {
                "found": count,
                "watermarked": 0,
                "skipped": 0,
                "skipped_files": [],
            }

    if not job_stats:
        slow_print("No images found in any 'stills' folders.")
        return

    # High-level "Searched X folder, found:" blocks
    for job_root_abs, stats in sorted(job_stats.items(), key=lambda x: str(x[0])):
        job_rel = job_root_abs.relative_to(ROOT_DIR)
        slow_print(f"Searched \"{job_rel}\" folder, found:")
        for stills_dir in sorted(job_stills[job_root_abs], key=lambda p: str(p)):
            path_rel = stills_dir.relative_to(ROOT_DIR)
            slow_print(f"  - {path_rel}")
        slow_print()

    # Detailed per-stills scan lines (only for folders with images)
    scan_messages = []
    for job_root_abs in sorted(job_stats.keys(), key=lambda p: str(p)):
        for stills_dir in sorted(job_stills[job_root_abs], key=lambda p: str(p)):
            path_rel = stills_dir.relative_to(ROOT_DIR)
            count = len(per_stills_images[stills_dir])
            msg = f"Scanned stills folder inside {path_rel}, found {count} image(s)."
            scan_messages.append(msg)

    if scan_messages:
        max_len = max(len(m) for m in scan_messages)
        slow_line("-", max_len)
        for m in scan_messages:
            # Small random buffer before each "found X image(s)" line
            if SCAN_BUFFER_MAX > 0:
                delay = random.uniform(SCAN_BUFFER_MIN, SCAN_BUFFER_MAX)
                time.sleep(max(0.0, delay))
            slow_print(m)
        slow_line("-", max_len)

    slow_print()  # blank line before total
    slow_print(f"Total images found across all 'stills' folders: {total_images}")
    if total_images == 0:
        slow_print("Nothing to do. No matching image files.")
        return

    # Confirm with user before proceeding
    slow_print("Proceed with watermarking these images? [Y/N]: ", end="")
    answer = input().strip().lower()

    # Small pause after the user answers (for both Y/y and N/n)
    if POST_CONFIRM_DELAY_MAX > 0:
        delay = random.uniform(POST_CONFIRM_DELAY_MIN, POST_CONFIRM_DELAY_MAX)
        time.sleep(max(0.0, delay))

    # If user says no, abort using typewriter output
    if answer in ("n", "no"):
        slow_print("Aborted by user. No images were modified.")
        return

    # Anything other than yes is treated as invalid + abort
    if answer not in ("y", "yes"):
        slow_print("Input not recognised. Aborting without changes.")
        return

    # --- POST-CONFIRM "DRAMA" SECTION (YES path) ---

    # Type out "Starting watermarking..." with the same typewriter effect
    slow_print("\nStarting watermarking...")
    slow_print()  # blank line

    # First pause after confirmation, before the first [1/N] line
    if POST_CONFIRM_DELAY_MAX > 0:
        delay = random.uniform(POST_CONFIRM_DELAY_MIN, POST_CONFIRM_DELAY_MAX)
        time.sleep(max(0.0, delay))

    # Only iterate over folders that actually have images
    stills_with_images = []
    for job_root_abs in sorted(job_stats.keys(), key=lambda p: str(p)):
        stills_with_images.extend(sorted(job_stills[job_root_abs], key=lambda p: str(p)))

    num_stills_dirs = len(stills_with_images)

    if num_stills_dirs == 0:
        slow_print("Nothing to do. No 'stills' folders with images.")
        return

    # --- HEADERS + CONVERSION-TIME MEASUREMENT ---

    # Print first header before starting conversions
    first_stills = stills_with_images[0]
    first_header = build_header_line(1, num_stills_dirs, first_stills)
    slow_print(first_header)
    if POST_CONFIRM_DELAY_MAX > 0:
        delay = random.uniform(POST_CONFIRM_DELAY_MIN, POST_CONFIRM_DELAY_MAX)
        time.sleep(max(0.0, delay))

    total_processed = 0
    conversion_time = 0.0  # only time spent inside the image loops

    for idx, stills_dir in enumerate(stills_with_images, start=1):
        image_files = per_stills_images[stills_dir]
        output_dir = stills_dir.parent / OUTPUT_FOLDER_NAME
        stats = folder_stats[stills_dir]

        # Conversion batch timing for this stills folder
        batch_start = time.perf_counter()
        for img_path in image_files:
            out_path = output_dir / img_path.name
            if watermark_image(img_path, out_path):
                total_processed += 1
                stats["watermarked"] += 1
            else:
                stats["skipped"] += 1
                stats["skipped_files"].append(img_path.name)
        batch_end = time.perf_counter()
        conversion_time += (batch_end - batch_start)

        print()  # blank line after this folder's images

        # If there is another stills folder, do the "pause + header + pause" drama
        if idx < num_stills_dirs:
            next_dir = stills_with_images[idx]  # zero-based index
            next_header = build_header_line(idx + 1, num_stills_dirs, next_dir)

            # Pause after the last ".jpg"
            if POST_CONFIRM_DELAY_MAX > 0:
                delay = random.uniform(POST_CONFIRM_DELAY_MIN, POST_CONFIRM_DELAY_MAX)
                time.sleep(max(0.0, delay))

            # Typewriter for next [i/n] header
            slow_print(next_header)

            # Second pause before actually starting next batch
            if POST_CONFIRM_DELAY_MAX > 0:
                delay = random.uniform(POST_CONFIRM_DELAY_MIN, POST_CONFIRM_DELAY_MAX)
                time.sleep(max(0.0, delay))

    # Pause after last ".jpg" line before summary (does not affect conversion_time)
    if POST_CONFIRM_DELAY_MAX > 0:
        delay = random.uniform(POST_CONFIRM_DELAY_MIN, POST_CONFIRM_DELAY_MAX)
        time.sleep(max(0.0, delay))

    # --- FINAL SUMMARY (CONSOLE) ---

    num_stills_with_images = len(folder_stats)

    summary1 = (
        f"Found {num_stills_with_images} 'stills' folders with images."
    )
    summary2 = f"Scanned folder tree and found {total_images} images."
    summary3 = (
        f"Watermarked {total_processed} out of {total_images} images "
        f"in {conversion_time:.2f} seconds."
    )

    # Per-folder summary lines like:
    # BALCLUTHA...\stills: watermarked X of Y images.
    per_folder_lines = []
    for job_root_abs in sorted(job_stats.keys(), key=lambda p: str(p)):
        for stills_dir in sorted(job_stills[job_root_abs], key=lambda p: str(p)):
            if stills_dir not in folder_stats:
                continue
            stats = folder_stats[stills_dir]
            rel_path = stills_dir.relative_to(ROOT_DIR)
            line = (
                f"{rel_path}: watermarked "
                f"{stats['watermarked']} of {stats['found']} images."
            )
            per_folder_lines.append(line)

    # Top line length: longest of summary1 + per-folder lines
    all_for_top = [summary1] + per_folder_lines
    top_len = max(len(s) for s in all_for_top)
    bottom_len = len(summary3)

    slow_line("-", top_len)
    slow_print(summary1)
    for line in per_folder_lines:
        slow_print(line)
    slow_print(summary2)
    slow_print(summary3)
    slow_line("-", bottom_len)

    # --- WRITE LOG FILE ---

    log_path = write_log(
        job_stats=job_stats,
        job_stills=job_stills,
        folder_stats=folder_stats,
        total_images=total_images,
        total_processed=total_processed,
        conversion_time=conversion_time,
    )

    rel_log = log_path.relative_to(ROOT_DIR)
    slow_print(f"Log written to '{rel_log}'.")


if __name__ == "__main__":
    main()
    # Prevent the window from closing immediately when double-clicked
    try:
        input("\nDone. Press Enter to close this window...")
    except EOFError:
        pass
