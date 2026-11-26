from __future__ import annotations

import tkinter.font as tkfont

from app_support import (
    tk,
    ttk,
)

class ThemeMixin:
    def _apply_theme(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        if self.high_contrast.get():
            background = "#000000"
            surface = "#000000"
            sidebar_background = "#000000"
            foreground = "#ffffff"
            muted = "#e6e6e6"
            field = "#000000"
            accent = "#ffff00"
            select_background = "#005fcc"
            button_active = "#333333"
            completed_color = "#7fff00"
            active_color = "#00ffff"
            failed_color = "#ff8080"
            other_color = "#ffff00"
        elif self.dark_mode.get():
            background = "#121214"
            surface = "#1a1a1e"
            sidebar_background = "#151519"
            foreground = "#ededed"
            muted = "#b7b7c0"
            field = "#18181d"
            accent = "#1ba987"
            select_background = "#28554b"
            button_active = "#303038"
            completed_color = "#65d6a6"
            active_color = "#62c9ed"
            failed_color = "#ff8585"
            other_color = "#e8c675"
        else:
            background = "#f3f5f8"
            surface = "#ffffff"
            sidebar_background = "#e9eef4"
            foreground = "#182230"
            muted = "#526174"
            field = "#ffffff"
            accent = "#1769aa"
            select_background = "#cfe4f8"
            button_active = "#e3ebf4"
            completed_color = "#167346"
            active_color = "#087d9d"
            failed_color = "#b42318"
            other_color = "#805b00"
        base_font = tkfont.nametofont("TkDefaultFont")
        base_font.configure(size=12 if self.large_text.get() else 10)
        self.root.option_add("*Font", base_font)
        heading_font_size = 11 if self.large_text.get() else 9
        title_font_size = 12 if self.large_text.get() else 10
        hint_font_size = 11 if self.large_text.get() else 9
        card_font_size = 12 if self.large_text.get() else 10
        style.configure(
            ".", background=background, foreground=foreground, font=base_font
        )
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=foreground)
        style.configure(
            "TNotebook", background=background, borderwidth=0, tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab", background=surface, foreground=foreground,
            padding=(12, 8), focuscolor=surface,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", accent), ("active", button_active)],
            foreground=[("selected", "#ffffff"), ("active", foreground)],
        )
        style.configure(
            "TLabelframe", background=background, foreground=foreground,
            bordercolor=muted,
        )
        style.configure(
            "TLabelframe.Label", background=background, foreground=foreground,
        )
        style.configure("Sidebar.TFrame", background=sidebar_background)
        style.configure(
            "SidebarTitle.TLabel", background=sidebar_background, foreground=foreground,
            font=("Segoe UI", title_font_size, "bold"),
        )
        style.configure(
            "SidebarHint.TLabel", background=sidebar_background, foreground=muted,
            font=("Segoe UI", hint_font_size),
        )
        style.configure(
            "Navigation.TButton", background=sidebar_background, foreground=foreground,
            anchor="w", padding=(12, 9), borderwidth=0,
        )
        style.map(
            "Navigation.TButton",
            background=[("active", button_active), ("pressed", button_active)],
            foreground=[("disabled", muted), ("active", foreground)],
        )
        style.configure(
            "Navigation.TMenubutton", background=sidebar_background,
            foreground=foreground, anchor="w", padding=(12, 9), borderwidth=0,
        )
        style.map(
            "Navigation.TMenubutton",
            background=[("active", button_active), ("pressed", button_active)],
            foreground=[("active", foreground)],
        )
        style.configure(
            "NavigationActive.TButton", background=select_background,
            foreground=foreground, anchor="w", padding=(12, 9), borderwidth=0,
        )
        style.map(
            "NavigationActive.TButton",
            background=[("active", select_background), ("pressed", select_background)],
            foreground=[("active", foreground)],
        )
        style.configure("Card.TFrame", background=surface)
        style.configure(
            "Card.TLabel",
            background=surface,
            foreground=foreground,
            font=("Segoe UI", card_font_size, "bold"),
        )
        style.configure(
            "TButton",
            background=surface,
            foreground=foreground,
            padding=(10, 5),
            borderwidth=1,
            focuscolor=accent,
        )
        style.map(
            "TButton",
            background=[("disabled", background), ("pressed", button_active), ("active", button_active)],
            foreground=[("disabled", muted)],
        )
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#ffffff",
            padding=(12, 6),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", muted), ("pressed", select_background), ("active", select_background)],
            foreground=[("disabled", background), ("!disabled", "#ffffff")],
        )
        # Premium Smart VLC preview styles. The video stage stays cinematic,
        # while the surrounding controls follow the active app theme.
        preview_stage = "#000000" if self.high_contrast.get() else "#081426"
        preview_accent = accent
        self._preview_timeline_colors = {
            "track": muted if self.high_contrast.get() else (
                "#536273" if self.dark_mode.get() else "#b7c5d5"
            ),
            "played": preview_accent,
            "handle": "#ffffff" if not self.high_contrast.get() else "#ffff00",
        }
        preview_toolbar = "#000000" if self.high_contrast.get() else (
            "#202b3c" if self.dark_mode.get() else "#edf3fa"
        )
        style.configure(
            "Preview.Status.TLabel",
            background=surface,
            foreground=preview_accent,
            padding=(9, 4),
            font=("Segoe UI", hint_font_size, "bold"),
        )
        style.configure(
            "Preview.Toolbar.TFrame",
            background=preview_toolbar,
            relief="flat",
        )
        style.configure(
            "Preview.Muted.TLabel",
            background=preview_toolbar,
            foreground=muted,
            font=("Segoe UI", hint_font_size, "bold"),
        )
        style.configure(
            "Preview.Value.TLabel",
            background=preview_toolbar,
            foreground=foreground,
            font=("Segoe UI", card_font_size, "bold"),
        )
        style.configure(
            "Preview.Count.TLabel",
            background=surface, foreground=muted,
            font=("Segoe UI", hint_font_size, "bold"),
        )
        style.configure(
            "Preview.Section.TLabel",
            background=surface,
            foreground=foreground,
            font=("Segoe UI", card_font_size, "bold"),
        )
        style.configure(
            "Preview.StatusText.TLabel",
            background=surface,
            foreground=muted,
            font=("Segoe UI", hint_font_size),
        )
        style.configure(
            "Preview.Empty.TLabel",
            background=preview_stage,
            foreground="#dcecff" if not self.high_contrast.get() else "#ffff00",
            font=("Segoe UI", card_font_size, "bold"),
        )
        style.configure(
            "Preview.Icon.TButton",
            background=preview_toolbar,
            foreground=foreground,
            padding=(11, 9),
            borderwidth=0,
            focuscolor=preview_accent,
            font=("Segoe UI Symbol", 12, "bold"),
        )
        style.map(
            "Preview.Icon.TButton",
            background=[("pressed", button_active), ("active", button_active)],
            foreground=[("disabled", muted), ("active", preview_accent)],
        )
        style.configure(
            "Preview.Play.TButton",
            background=preview_accent,
            foreground="#ffffff" if not self.high_contrast.get() else "#000000",
            padding=(12, 10),
            borderwidth=0,
            focuscolor=preview_accent,
            font=("Segoe UI Symbol", 12, "bold"),
        )
        style.map(
            "Preview.Play.TButton",
            background=[("disabled", muted), ("pressed", select_background), ("active", select_background)],
            foreground=[("disabled", background)],
        )
        style.configure("TCheckbutton", background=background, foreground=foreground)
        style.map(
            "TCheckbutton",
            background=[("active", background)],
            foreground=[("disabled", muted), ("active", foreground)],
        )
        style.configure(
            "TEntry",
            fieldbackground=field,
            foreground=foreground,
            borderwidth=1,
            padding=5,
        )
        style.configure(
            "TCombobox",
            fieldbackground=field,
            foreground=foreground,
            arrowcolor=foreground,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", field), ("disabled", background)],
            foreground=[("readonly", foreground), ("disabled", muted)],
            selectbackground=[("readonly", select_background)],
            selectforeground=[("readonly", foreground)],
        )
        style.configure("TSeparator", background=muted)
        style.configure(
            "Treeview",
            background=field,
            fieldbackground=field,
            foreground=foreground,
            rowheight=36 if self.large_text.get() else 28,
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", select_background)],
            foreground=[("selected", foreground)],
        )
        style.configure(
            "Treeview.Heading",
            background=surface,
            foreground=foreground,
            padding=(8, 7),
            font=("Segoe UI", heading_font_size, "bold"),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", button_active)],
            foreground=[("active", foreground)],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=accent,
            troughcolor=surface,
            bordercolor=surface,
        )
        style.configure(
            "Vertical.TScrollbar",
            background=surface,
            troughcolor=background,
            arrowcolor=foreground,
        )
        self.root.configure(background=background)
        self.sidebar_canvas.configure(background=sidebar_background)
        self._style_menu(self.history_menu, surface, foreground, muted, accent)
        self._style_menu(self.tools_menu, surface, foreground, muted, accent)
        self.settings_window.configure(background=background)
        self.jobs.tag_configure("hidden", foreground=muted)
        self.jobs.tag_configure("status_complete", foreground=completed_color)
        self.jobs.tag_configure("status_active", foreground=active_color)
        self.jobs.tag_configure("status_failed", foreground=failed_color)
        self.jobs.tag_configure("status_other", foreground=other_color)
        for job_id in self._queue_job_ids:
            self._refresh_job_style(job_id)
        self.speed_graph.configure(background=field)
        self._draw_speed_graph()

    @staticmethod
    def _style_menu(
        menu: tk.Menu,
        background: str,
        foreground: str,
        muted: str,
        accent: str,
    ) -> None:
        menu.configure(
            background=background,
            foreground=foreground,
            activebackground=accent,
            activeforeground="#ffffff",
            disabledforeground=muted,
            selectcolor=accent,
            borderwidth=0,
            relief="flat",
        )

    def _style_context_menu(self, menu: tk.Menu) -> None:
        if self.high_contrast.get():
            palette = ("#000000", "#ffffff", "#e6e6e6", "#ffff00")
        elif self.dark_mode.get():
            palette = ("#1a1a1e", "#ededed", "#b7b7c0", "#1ba987")
        else:
            palette = ("#ffffff", "#182230", "#526174", "#1769aa")
        self._style_menu(menu, *palette)
