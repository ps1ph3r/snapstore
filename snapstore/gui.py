from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

from .diff import diff_snapshots
from .models import Repository, open_repo
from .restore import restore
from .result import Err, Ok
from .snapshot import create_snapshot, delete_snapshot, get_snapshot_by_id, list_snapshots
from .status import compute_status

# Clean Desktop Color Palette
COLOR_BG = "#f1f5f9"         # Slate background
COLOR_SURFACE = "#ffffff"    # Pure white panels
COLOR_BORDER = "#cbd5e1"     # Slate border
COLOR_TEXT = "#0f172a"       # Slate 900 text
COLOR_MUTED = "#64748b"      # Slate 500 secondary text
COLOR_BLUE = "#2563eb"       # Primary brand blue
COLOR_BLUE_HOVER = "#1d4ed8" # Blue hover
COLOR_GREEN = "#16a34a"      # Status green
COLOR_AMBER = "#d97706"      # Status amber
COLOR_RED = "#dc2626"        # Danger red


def detect_fonts(root: tk.Tk | None = None) -> tuple[str, str]:
    """Detect available system fonts, prioritizing Inter and JetBrains Mono."""
    try:
        available = set(tkfont.families(root))
    except Exception:
        return "TkDefaultFont", "TkFixedFont"

    ui_candidates = [
        "Inter",
        "SF Pro Text",
        "SF Pro",
        "Segoe UI",
        "Noto Sans",
        "Liberation Sans",
        "DejaVu Sans",
    ]
    mono_candidates = [
        "JetBrains Mono",
        "JetBrainsMono Nerd Font",
        "SF Mono",
        "Noto Sans Mono",
        "Liberation Mono",
        "DejaVu Sans Mono",
        "Consolas",
    ]

    ui_font = next((f for f in ui_candidates if f in available), "TkDefaultFont")
    mono_font = next((f for f in mono_candidates if f in available), "TkFixedFont")
    return ui_font, mono_font


class SnapStoreGUI:
    """Standard, clean desktop user interface for SnapStore."""

    def __init__(self, root: tk.Tk, initial_dir: str | Path | None = None):
        self.root = root
        self.root.title("SnapStore — Snapshot Backup & Recovery")
        self.root.geometry("940x580")
        self.root.minsize(780, 440)
        self.root.configure(bg=COLOR_BG)

        self.current_dir = Path(initial_dir or Path.cwd()).resolve()
        self.font_ui, self.font_mono = detect_fonts(self.root)

        self._configure_styles()
        self._build_ui()
        self.refresh()

    def _configure_styles(self):
        """Configure proportional ttk widgets with crisp typography."""
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        # Container styling
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Surface.TFrame", background=COLOR_SURFACE)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=(self.font_ui, 10))
        style.configure("Surface.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT, font=(self.font_ui, 10))
        style.configure("Muted.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED, font=(self.font_ui, 9))

        # Primary Button (Blue action button)
        style.configure(
            "Primary.TButton",
            background=COLOR_BLUE,
            foreground="white",
            font=(self.font_ui, 10, "bold"),
            borderwidth=0,
            padding=(14, 6),
        )
        style.map(
            "Primary.TButton",
            background=[("active", COLOR_BLUE_HOVER), ("disabled", "#94a3b8")],
            foreground=[("disabled", "#f8fafc")],
        )

        # Secondary Button (Neutral action button)
        style.configure(
            "Secondary.TButton",
            background="#e2e8f0",
            foreground=COLOR_TEXT,
            font=(self.font_ui, 9),
            borderwidth=0,
            padding=(10, 5),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#cbd5e1"), ("disabled", "#f1f5f9")],
            foreground=[("disabled", "#94a3b8")],
        )

        # Treeview (Snapshots table with clean standard row height)
        style.configure(
            "Treeview",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            fieldbackground=COLOR_SURFACE,
            borderwidth=0,
            font=(self.font_ui, 9),
            rowheight=26,
        )
        style.map(
            "Treeview",
            background=[("selected", COLOR_BLUE)],
            foreground=[("selected", "white")],
        )
        style.configure(
            "Treeview.Heading",
            background="#e2e8f0",
            foreground=COLOR_TEXT,
            font=(self.font_ui, 9, "bold"),
            borderwidth=0,
            padding=(6, 6),
        )
        style.map("Treeview.Heading", background=[("active", "#cbd5e1")])

    def _build_ui(self):
        """Construct a balanced, compact desktop layout."""
        main_box = ttk.Frame(self.root, padding="14")
        main_box.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # 1. Top Bar: App Title + Target Folder Path + Primary Actions
        # -------------------------------------------------------------
        top_bar = ttk.Frame(main_box)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        # Title / Brand
        brand_lbl = tk.Label(
            top_bar,
            text="SnapStore",
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            font=(self.font_ui, 13, "bold"),
        )
        brand_lbl.pack(side=tk.LEFT, padx=(0, 14))

        # Folder Input Entry
        self.dir_var = tk.StringVar(value=str(self.current_dir))
        self.dir_entry = tk.Entry(
            top_bar,
            textvariable=self.dir_var,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief=tk.FLAT,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            font=(self.font_ui, 9),
        )
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 8))
        self.dir_entry.bind("<Return>", lambda _: self.refresh())

        # Browse Button
        browse_btn = ttk.Button(
            top_bar,
            text="Browse...",
            style="Secondary.TButton",
            command=self._browse_directory,
        )
        browse_btn.pack(side=tk.LEFT, padx=(0, 12))

        # Primary Action Button (Create Snapshot or Initialize)
        self.snapshot_btn = ttk.Button(
            top_bar,
            text="+ Take Snapshot",
            style="Primary.TButton",
            command=self._create_snapshot,
        )
        self.snapshot_btn.pack(side=tk.RIGHT)

        self.init_btn = ttk.Button(
            top_bar,
            text="Initialize Repo",
            style="Primary.TButton",
            command=self._init_repo,
        )

        # -------------------------------------------------------------
        # 2. Compact Status Strip
        # -------------------------------------------------------------
        status_bar = tk.Frame(
            main_box,
            bg=COLOR_SURFACE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        status_bar.pack(fill=tk.X, pady=(0, 10))

        self.status_icon = tk.Label(
            status_bar,
            text="●",
            bg=COLOR_SURFACE,
            fg=COLOR_MUTED,
            font=(self.font_ui, 10, "bold"),
        )
        self.status_icon.pack(side=tk.LEFT, padx=(0, 6))

        self.status_text = tk.Label(
            status_bar,
            text="Checking repository status...",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=(self.font_ui, 9),
            anchor="w",
        )
        self.status_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.snapshot_count_lbl = tk.Label(
            status_bar,
            text="",
            bg=COLOR_SURFACE,
            fg=COLOR_MUTED,
            font=(self.font_ui, 9),
        )
        self.snapshot_count_lbl.pack(side=tk.RIGHT)

        # -------------------------------------------------------------
        # 3. Snapshots History Table
        # -------------------------------------------------------------
        table_frame = tk.Frame(
            main_box,
            bg=COLOR_SURFACE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = ("id", "time", "files", "parent")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("id", text="Snapshot ID", anchor=tk.W)
        self.tree.heading("time", text="Timestamp", anchor=tk.W)
        self.tree.heading("files", text="Tracked Files", anchor=tk.CENTER)
        self.tree.heading("parent", text="Parent ID", anchor=tk.W)

        self.tree.column("id", width=110, minwidth=90, anchor=tk.W)
        self.tree.column("time", width=200, minwidth=160, anchor=tk.W)
        self.tree.column("files", width=110, minwidth=80, anchor=tk.CENTER)
        self.tree.column("parent", width=140, minwidth=100, anchor=tk.W)

        # Subtle zebra striping
        self.tree.tag_configure("even", background=COLOR_SURFACE)
        self.tree.tag_configure("odd", background="#f8fafc")

        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select_snapshot)
        self.tree.bind("<Double-1>", lambda _: self._view_diff())

        # -------------------------------------------------------------
        # 4. Bottom Action Bar
        # -------------------------------------------------------------
        bottom_bar = ttk.Frame(main_box)
        bottom_bar.pack(fill=tk.X)

        self.diff_btn = ttk.Button(
            bottom_bar,
            text="Inspect Diff",
            style="Secondary.TButton",
            command=self._view_diff,
            state=tk.DISABLED,
        )
        self.diff_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.restore_btn = ttk.Button(
            bottom_bar,
            text="Restore...",
            style="Secondary.TButton",
            command=self._restore_snapshot,
            state=tk.DISABLED,
        )
        self.restore_btn.pack(side=tk.LEFT)

        self.delete_btn = ttk.Button(
            bottom_bar,
            text="Delete",
            style="Secondary.TButton",
            command=self._delete_snapshot,
            state=tk.DISABLED,
        )
        self.delete_btn.pack(side=tk.LEFT, padx=(8, 0))

        refresh_btn = ttk.Button(
            bottom_bar,
            text="Refresh",
            style="Secondary.TButton",
            command=self.refresh,
        )
        refresh_btn.pack(side=tk.RIGHT)

    def _browse_directory(self):
        chosen = filedialog.askdirectory(initialdir=str(self.current_dir), title="Select Project Folder")
        if chosen:
            self.current_dir = Path(chosen).resolve()
            self.dir_var.set(str(self.current_dir))
            self.refresh()

    def refresh(self):
        """Update repository view, status indicator, and snapshot history."""
        self.current_dir = Path(self.dir_var.get()).resolve()
        repo = Repository(self.current_dir)

        # Clear existing table items
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.diff_btn.config(state=tk.DISABLED)
        self.restore_btn.config(state=tk.DISABLED)
        self.delete_btn.config(state=tk.DISABLED)

        if not repo.is_initialized():
            self.status_icon.config(text="○", fg=COLOR_AMBER)
            self.status_text.config(text="Directory not initialized. Click 'Initialize Repo' to start tracking snapshots.")
            self.snapshot_count_lbl.config(text="")
            self.snapshot_btn.pack_forget()
            self.init_btn.pack(side=tk.RIGHT)
            return

        # Show Take Snapshot button
        self.init_btn.pack_forget()
        self.snapshot_btn.pack(side=tk.RIGHT)
        self.snapshot_btn.config(state=tk.NORMAL)

        # Populate snapshots list
        snapshots = list_snapshots(repo)
        self.snapshot_count_lbl.config(text=f"{len(snapshots)} snapshot(s)")

        for i, s in enumerate(snapshots):
            ts = datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d  %H:%M:%S")
            row_tag = "even" if i % 2 == 0 else "odd"
            parent_display = s.parent_id if s.parent_id else "(root)"
            self.tree.insert(
                "",
                tk.END,
                iid=s.snapshot_id,
                values=(s.snapshot_id, ts, f"{len(s.files)} files", parent_display),
                tags=(row_tag,),
            )

        # Evaluate working tree status
        match compute_status(repo):
            case Ok(diff):
                if not diff:
                    self.status_icon.config(text="●", fg=COLOR_GREEN)
                    self.status_text.config(text="Working tree clean — no uncommitted changes.")
                    self.snapshot_btn.config(state=tk.DISABLED)
                else:
                    parts = []
                    if diff.added:
                        parts.append(f"{len(diff.added)} added")
                    if diff.modified:
                        parts.append(f"{len(diff.modified)} modified")
                    if diff.deleted:
                        parts.append(f"{len(diff.deleted)} deleted")
                    self.status_icon.config(text="●", fg=COLOR_AMBER)
                    self.status_text.config(text=f"Unsaved changes: {', '.join(parts)}")
                    self.snapshot_btn.config(state=tk.NORMAL)
            case Err(err):
                self.status_icon.config(text="✕", fg=COLOR_RED)
                self.status_text.config(text=f"Error checking status: {err}")

    def _init_repo(self):
        repo = Repository(self.current_dir)
        repo.objects_dir.mkdir(parents=True, exist_ok=True)
        repo.snapshots_dir.mkdir(parents=True, exist_ok=True)
        messagebox.showinfo("Initialized", f"SnapStore initialized in:\n{repo.snapstore_dir}")
        self.refresh()

    def _create_snapshot(self):
        match open_repo(self.current_dir):
            case Err(err):
                messagebox.showerror("Error", err)
            case Ok(repo):
                match create_snapshot(repo):
                    case Ok(manifest):
                        messagebox.showinfo(
                            "Snapshot Created",
                            f"Snapshot ID: {manifest.snapshot_id}\nTracked {len(manifest.files)} file(s).",
                        )
                        self.refresh()
                    case Err(err):
                        messagebox.showerror("Failed to Create Snapshot", err)

    def _on_select_snapshot(self, _event):
        has_selection = bool(self.tree.selection())
        state = tk.NORMAL if has_selection else tk.DISABLED
        self.diff_btn.config(state=state)
        self.restore_btn.config(state=state)
        self.delete_btn.config(state=state)

    def _delete_snapshot(self):
        selected = self.tree.selection()
        if not selected:
            return

        snapshot_id = selected[0]
        if not messagebox.askyesno(
            "Delete Snapshot",
            f"Are you sure you want to delete snapshot [{snapshot_id}]?\nThis will remove it from snapshot history.",
            icon="warning",
        ):
            return

        repo = Repository(self.current_dir)
        match delete_snapshot(repo, snapshot_id):
            case Ok(msg):
                messagebox.showinfo("Deleted", msg)
                self.refresh()
            case Err(err):
                messagebox.showerror("Delete Failed", err)

    def _view_diff(self):
        selected = self.tree.selection()
        if not selected:
            return

        snapshot_id = selected[0]
        repo = Repository(self.current_dir)

        match get_snapshot_by_id(repo, snapshot_id):
            case Err(err):
                messagebox.showerror("Error", err)
                return
            case Ok(snap):
                diff_text = []
                if snap.parent_id:
                    p_res = get_snapshot_by_id(repo, snap.parent_id)
                    if p_res.is_ok():
                        p_snap = p_res.unwrap()
                        diff_text.append(f"Changes compared to parent [{p_snap.snapshot_id}]:\n")
                        diff_text.append(diff_snapshots(p_snap, snap).long_format())
                    else:
                        diff_text.append(f"Parent snapshot {snap.parent_id} not found.")
                else:
                    diff_text.append(f"Snapshot [{snap.snapshot_id}] is the initial snapshot.\n")
                    diff_text.append("Files stored in this snapshot:")
                    for path in sorted(snap.files.keys()):
                        diff_text.append(f"    {path}")

                self._show_diff_window(f"Snapshot {snapshot_id}", "\n".join(diff_text))

    def _restore_snapshot(self):
        selected = self.tree.selection()
        if not selected:
            return

        snapshot_id = selected[0]
        dest = filedialog.askdirectory(title=f"Select Target Directory for Restore [{snapshot_id}]")
        if not dest:
            return

        repo = Repository(self.current_dir)
        match restore(repo, snapshot_id, Path(dest)):
            case Ok(count):
                messagebox.showinfo(
                    "Restore Completed",
                    f"Restored {count} file(s) from snapshot [{snapshot_id}] to:\n{dest}",
                )
            case Err(err):
                messagebox.showerror("Restore Failed", err)

    def _show_diff_window(self, title: str, content: str):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Diff — {title}")
        dialog.geometry("780x500")
        dialog.minsize(600, 360)
        dialog.configure(bg=COLOR_BG)

        wrapper = tk.Frame(dialog, bg=COLOR_BG, padx=14, pady=14)
        wrapper.pack(fill=tk.BOTH, expand=True)

        header = tk.Label(
            wrapper,
            text=title,
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            font=(self.font_ui, 11, "bold"),
        )
        header.pack(anchor=tk.W, pady=(0, 8))

        text_card = tk.Frame(
            wrapper,
            bg=COLOR_SURFACE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        text_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        txt = tk.Text(
            text_card,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            wrap=tk.WORD,
            font=(self.font_mono, 9),
            padx=10,
            pady=8,
            relief=tk.FLAT,
            borderwidth=0,
        )
        scroll = ttk.Scrollbar(text_card, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)

        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Monospace syntax coloring
        txt.tag_configure("add", foreground=COLOR_GREEN, font=(self.font_mono, 9, "bold"))
        txt.tag_configure("del", foreground=COLOR_RED, font=(self.font_mono, 9, "bold"))
        txt.tag_configure("mod", foreground=COLOR_AMBER, font=(self.font_mono, 9, "bold"))
        txt.tag_configure("header", foreground=COLOR_BLUE, font=(self.font_mono, 9, "bold"))

        for line in content.splitlines(keepends=True):
            if line.startswith("ADDED") or line.startswith("+++"):
                txt.insert(tk.END, line, "add")
            elif line.startswith("DELETED") or line.startswith("---"):
                txt.insert(tk.END, line, "del")
            elif line.startswith("MODIFIED"):
                txt.insert(tk.END, line, "mod")
            elif line.startswith("Changes") or line.startswith("Snapshot ["):
                txt.insert(tk.END, line, "header")
            else:
                txt.insert(tk.END, line)

        txt.config(state=tk.DISABLED)

        close_btn = ttk.Button(wrapper, text="Close", style="Secondary.TButton", command=dialog.destroy)
        close_btn.pack(side=tk.RIGHT)


def launch_gui(initial_dir: str | Path | None = None):
    """Launch the SnapStore clean desktop graphical interface."""
    root = tk.Tk()
    SnapStoreGUI(root, initial_dir)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
