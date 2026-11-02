"""Minimal, clean Tkinter graphical user interface for SnapStore."""

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .diff import diff_snapshot_vs_current, diff_snapshots
from .models import Repository, open_repo
from .restore import restore
from .result import Err, Ok
from .snapshot import create_snapshot, get_snapshot_by_id, list_snapshots
from .status import compute_status


class SnapStoreGUI:
    """Simple and intuitive graphical interface for SnapStore."""

    def __init__(self, root: tk.Tk, initial_dir: str | Path | None = None):
        self.root = root
        self.root.title("SnapStore — Local Backup & Recovery")
        self.root.geometry("720x540")
        self.root.minsize(620, 440)

        self.current_dir = Path(initial_dir or Path.cwd()).resolve()

        self._setup_style()
        self._build_ui()
        self.refresh()

    def _setup_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Header.TLabel", font=("Helvetica", 11, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 10))
        style.configure("Primary.TButton", font=("Helvetica", 10, "bold"))

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="14")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Directory Selection Bar
        dir_frame = ttk.LabelFrame(main_frame, text="Target Folder", padding="10")
        dir_frame.pack(fill=tk.X, pady=(0, 10))

        self.dir_var = tk.StringVar(value=str(self.current_dir))
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, font=("Helvetica", 10))
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        browse_btn = ttk.Button(dir_frame, text="Browse...", command=self._browse_directory)
        browse_btn.pack(side=tk.LEFT)

        # 2. Status & Quick Actions Bar
        status_frame = ttk.LabelFrame(main_frame, text="Status & Backup", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(
            status_frame,
            text="Checking folder...",
            style="Status.TLabel"
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.init_btn = ttk.Button(
            status_frame,
            text="Initialize SnapStore",
            command=self._init_repo
        )

        self.snapshot_btn = ttk.Button(
            status_frame,
            text="📸 Create Snapshot",
            style="Primary.TButton",
            command=self._create_snapshot
        )
        self.snapshot_btn.pack(side=tk.RIGHT, padx=(8, 0))

        # 3. Snapshot History Table
        history_frame = ttk.LabelFrame(main_frame, text="Saved Snapshots (Newest First)", padding="10")
        history_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("id", "time", "files", "parent")
        self.tree = ttk.Treeview(history_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("id", text="Snapshot ID")
        self.tree.heading("time", text="Created On")
        self.tree.heading("files", text="Files")
        self.tree.heading("parent", text="Parent ID")

        self.tree.column("id", width=110, anchor=tk.CENTER)
        self.tree.column("time", width=190, anchor=tk.W)
        self.tree.column("files", width=80, anchor=tk.CENTER)
        self.tree.column("parent", width=110, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select_snapshot)

        # 4. Action Buttons Bar
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X)

        self.diff_btn = ttk.Button(
            action_frame,
            text="🔍 View Changes (Diff)",
            command=self._view_diff,
            state=tk.DISABLED
        )
        self.diff_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.restore_btn = ttk.Button(
            action_frame,
            text="🔄 Restore Snapshot...",
            command=self._restore_snapshot,
            state=tk.DISABLED
        )
        self.restore_btn.pack(side=tk.LEFT)

        refresh_btn = ttk.Button(action_frame, text="⚡ Refresh", command=self.refresh)
        refresh_btn.pack(side=tk.RIGHT)

    def _browse_directory(self):
        chosen = filedialog.askdirectory(initialdir=str(self.current_dir), title="Select Folder")
        if chosen:
            self.current_dir = Path(chosen).resolve()
            self.dir_var.set(str(self.current_dir))
            self.refresh()

    def refresh(self):
        """Re-scan repository state, working tree status, and snapshot history."""
        self.current_dir = Path(self.dir_var.get()).resolve()
        repo = Repository(self.current_dir)

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.diff_btn.config(state=tk.DISABLED)
        self.restore_btn.config(state=tk.DISABLED)

        if not repo.is_initialized():
            self.status_label.config(
                text="⚠️ Folder not initialized. Click 'Initialize SnapStore' to start tracking.",
                foreground="#b26a00"
            )
            self.init_btn.pack(side=tk.RIGHT, padx=(8, 0))
            self.snapshot_btn.config(state=tk.DISABLED)
            return

        # Hide init button if already initialized
        self.init_btn.pack_forget()
        self.snapshot_btn.config(state=tk.NORMAL)

        # Populate snapshots
        snapshots = list_snapshots(repo)
        for s in snapshots:
            ts = datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            self.tree.insert(
                "",
                tk.END,
                iid=s.snapshot_id,
                values=(s.snapshot_id, ts, len(s.files), s.parent_id or "(root)")
            )

        # Check working tree changes
        match compute_status(repo):
            case Ok(diff):
                if not diff:
                    self.status_label.config(
                        text=f"✓ Clean: No changes since last snapshot ({len(snapshots)} snapshots stored)",
                        foreground="#008000"
                    )
                else:
                    changes = []
                    if diff.added:
                        changes.append(f"{len(diff.added)} added")
                    if diff.modified:
                        changes.append(f"{len(diff.modified)} modified")
                    if diff.deleted:
                        changes.append(f"{len(diff.deleted)} deleted")
                    self.status_label.config(
                        text=f"● Changes detected: {', '.join(changes)}",
                        foreground="#c00000"
                    )
            case Err(err):
                self.status_label.config(text=f"Status check error: {err}", foreground="#c00000")

    def _init_repo(self):
        repo = Repository(self.current_dir)
        repo.objects_dir.mkdir(parents=True, exist_ok=True)
        repo.snapshots_dir.mkdir(parents=True, exist_ok=True)
        messagebox.showinfo("SnapStore", f"Initialized SnapStore in:\n{repo.snapstore_dir}")
        self.refresh()

    def _create_snapshot(self):
        match open_repo(self.current_dir):
            case Err(err):
                messagebox.showerror("Error", err)
            case Ok(repo):
                match create_snapshot(repo):
                    case Ok(manifest):
                        messagebox.showinfo("Snapshot Created", f"Successfully saved snapshot {manifest.snapshot_id}!")
                        self.refresh()
                    case Err(err):
                        messagebox.showerror("Failed to Snapshot", err)

    def _on_select_snapshot(self, _event):
        selected = self.tree.selection()
        if selected:
            self.diff_btn.config(state=tk.NORMAL)
            self.restore_btn.config(state=tk.NORMAL)
        else:
            self.diff_btn.config(state=tk.DISABLED)
            self.restore_btn.config(state=tk.DISABLED)

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
                lines = []
                if snap.parent_id:
                    p_res = get_snapshot_by_id(repo, snap.parent_id)
                    if p_res.is_ok():
                        p_snap = p_res.unwrap()
                        lines.append(f"Changes from parent snapshot {p_snap.snapshot_id}:\n")
                        lines.append(diff_snapshots(p_snap, snap).long_format())
                    else:
                        lines.append(f"Parent snapshot {snap.parent_id} not found.")
                else:
                    lines.append(f"Snapshot '{snap.snapshot_id}' is the initial root snapshot (no parent).\n")
                    lines.append(f"Total files stored: {len(snap.files)}")

                self._show_text_dialog(f"Snapshot Details: {snapshot_id}", "\n".join(lines))

    def _restore_snapshot(self):
        selected = self.tree.selection()
        if not selected:
            return

        snapshot_id = selected[0]
        dest = filedialog.askdirectory(title=f"Select Destination Folder to Restore Snapshot {snapshot_id}")
        if not dest:
            return

        repo = Repository(self.current_dir)
        match restore(repo, snapshot_id, Path(dest)):
            case Ok(count):
                messagebox.showinfo(
                    "Restore Completed",
                    f"Successfully restored {count} file(s) from snapshot {snapshot_id} into:\n{dest}"
                )
            case Err(err):
                messagebox.showerror("Restore Failed", err)

    def _show_text_dialog(self, title: str, content: str):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("600x400")

        txt_frame = ttk.Frame(dialog, padding="10")
        txt_frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(txt_frame, wrap=tk.WORD, font=("Courier", 10))
        scroll = ttk.Scrollbar(txt_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scroll.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget.insert(tk.END, content)
        text_widget.config(state=tk.DISABLED)

        close_btn = ttk.Button(dialog, text="Close", command=dialog.destroy)
        close_btn.pack(pady=(0, 10))


def launch_gui(initial_dir: str | Path | None = None):
    """Launch the SnapStore Tkinter application."""
    root = tk.Tk()
    SnapStoreGUI(root, initial_dir)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
