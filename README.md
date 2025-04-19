# FileCascade

**FileCascade** is a lightweight desktop tool for organizing large collections of files into groups, based on the file modification times. Built with PySide6.

## Why?

I built FileCascade to solve a pretty niche problem I kept running into. I work with large sets of data that need to be categorized into folders for processing. Most of the grouping can be done automatically based on creation or modification time, but there's always a handful of files that need to be manually sorted. I made this tool to simplify that process. It groups and lists files based on a set time frame, and then lets me manually tweak the grouping with simple drag-and-drop. Once I'm happy with the final arrangement, I can copy them into their grouped folders in one click.

---

## Features

- **Automatic Grouping**: Group files by timestamp difference (e.g., files modified within 5 minutes).
- **Grouping Count**: Distribute files into a specified number of groups.
- **Customizable Folder Names**: Set your own naming pattern for destination folders.
- **Drag-and-Drop Reordering**: Rearrange files or move them between groups using a simple drag-and-drop interface.
- **Editable Group Names**: Customize group names before copying.
- **Copy, not Cut**: Files are copied to the destination folders, not moved.
---

## Installation

### From Source

1. Clone the repository:
   ```bash
   git clone https://github.com/unseensholar/FileCascade.git
   cd FileCascade
   ```

2. Run the app:
   ```bash
   python FileCascade.py
   ```

### Windows Executable

Download the pre-built `.exe` from [Releases](https://github.com/unseensholar/FileCascade/releases).

No installation required—just download and run.

---

## Requirements

- Python 3.8+
- PySide6

(Windows executable includes all dependencies.)

---

## Usage

1. Select a **Source Directory** containing the files.
2. Select a **Destination Directory** where organized folders will be created.
3. Choose grouping mode: **by time** or **manual group count**.
4. Choose the file extensions to handle (**.csv**, **.txt**. **.jpg**, etc).
5. Customize folder naming pattern and optionally edit group names.
6. Click **Copy Files to Destination**.


---

## License

This project is licensed under the **MIT License**—simple, permissive, and allows wide reuse.

> You are free to use, modify, and distribute this software with or without changes, provided you include the original license text.

(See [LICENSE](LICENSE) file for full terms.)

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Suggestions, bug reports, and improvements are warmly encouraged.

---

## Roadmap

- [x] Multi-format support (images, text files, etc.)
- [x] Configurable file extension filters
- [ ] Save/load group templates
- [x] Dark mode UI

---

Thank you for using **FileCascade**! ⭐ If you find it useful, please consider starring the repo.

