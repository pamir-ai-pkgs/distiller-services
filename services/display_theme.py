"""
E-ink Display Theme Configuration.

Centralized design system for the 122x250 e-ink display.
All spacing, sizing, and styling constants in one place.
"""

from dataclasses import dataclass


@dataclass
class DisplayDimensions:
    """Display physical dimensions for horizontal layout."""

    width: int = 250  # Horizontal orientation
    height: int = 122  # Horizontal orientation


@dataclass
class Spacing:
    """Spacing system for horizontal layouts."""

    # Base unit for spacing (all other spacing derived from this)
    unit: int = 4

    # Margins
    margin: int = 6  # Safe margin on all sides

    # Padding (reduced for horizontal layout)
    xs: int = 2  # Extra small
    sm: int = 3  # Small
    md: int = 4  # Medium
    lg: int = 6  # Large
    xl: int = 8  # Extra large
    xxl: int = 12  # Double extra large

    # Component spacing (optimized for horizontal)
    between_components: int = 6  # Space between major components
    between_lines: int = 2  # Space between text lines
    after_title: int = 6  # Space after titles
    after_section: int = 4  # Space after sections
    column_gap: int = 10  # Space between columns


@dataclass
class Typography:
    """Typography system with named styles."""

    # Font sizes
    size_xs: int = 10  # Extra small text
    size_sm: int = 11  # Small text
    size_md: int = 12  # Medium text
    size_lg: int = 14  # Large text

    # Line heights (font size + spacing)
    line_height_tight: int = 2  # Tight line spacing
    line_height_normal: int = 4  # Normal line spacing
    line_height_loose: int = 6  # Loose line spacing

    # Text styles (mapped to font family and size)
    styles: dict[str, dict] | None = None

    def __post_init__(self):
        """Initialize text styles after dataclass creation."""
        self.styles = {
            "title": {
                "font": "large",  # NotoSans-Bold 14pt
                "size": self.size_lg,
                "uppercase": True,
            },
            "subtitle": {
                "font": "medium",  # NotoSans-Bold 12pt
                "size": self.size_md,
                "uppercase": True,
            },
            "heading": {
                "font": "medium",  # NotoSans-Bold 12pt
                "size": self.size_md,
                "uppercase": True,
            },
            "label": {
                "font": "medium",  # NotoSans-Bold 12pt
                "size": self.size_md,
                "uppercase": True,
            },
            "body": {
                "font": "small",  # NotoSans-Bold 11pt
                "size": self.size_sm,
                "uppercase": False,
            },
            "value": {
                "font": "small",  # NotoSans-Bold 11pt
                "size": self.size_sm,
                "uppercase": False,
            },
            "caption": {
                "font": "xs",  # NotoSans-Bold 10pt
                "size": self.size_xs,
                "uppercase": False,
            },
            "button": {
                "font": "medium",  # NotoSans-Bold 12pt
                "size": self.size_md,
                "uppercase": True,
            },
        }


@dataclass
class Components:
    """Component size presets for horizontal layout."""

    # QR Code sizes (optimized for horizontal layout)
    qr_small: int = 60
    qr_medium: int = 70
    qr_large: int = 80

    # Progress bar (fits within right column)
    progress_bar_width: int = 125
    progress_bar_height: int = 14
    progress_bar_border: int = 2

    # Icons
    icon_small: int = 16
    icon_medium: int = 24
    icon_large: int = 32

    # Checkmark
    checkmark_size: int = 24
    checkmark_stroke: int = 3

    # Buttons (visual representation)
    button_height: int = 32
    button_padding_x: int = 12
    button_padding_y: int = 8
    button_border: int = 2


@dataclass
class Colors:
    """Color values for monochrome display."""

    black: int = 0  # Black pixels
    white: int = 1  # White pixels

    # Semantic colors (mapped to black/white)
    background: int = 1  # White background
    foreground: int = 0  # Black text/graphics
    primary: int = 0  # Primary elements (black)
    secondary: int = 1  # Secondary elements (white)


@dataclass
class Layout:
    """Layout configuration for horizontal display."""

    # Content area (display width minus margins)
    content_width: int = 238  # 250 - (2 * 6)
    content_height: int = 110  # 122 - (2 * 6)

    # Column widths for two-column layout
    left_column_width: int = 95  # Left column for titles/icons/QR
    right_column_width: int = 133  # Right column for content
    column_gap: int = 10  # Gap between columns

    # Alignment
    align_left: str = "left"
    align_center: str = "center"
    align_right: str = "right"
    align_top: str = "top"
    align_middle: str = "middle"
    align_bottom: str = "bottom"

    # Flow direction
    flow_vertical: str = "vertical"
    flow_horizontal: str = "horizontal"

    # Maximum text width for readability
    max_text_width: int = 133  # Right column width


class Theme:
    """Complete theme configuration for e-ink display."""

    def __init__(self):
        self.display = DisplayDimensions()
        self.spacing = Spacing()
        self.typography = Typography()
        self.components = Components()
        self.colors = Colors()
        self.layout = Layout()

    @property
    def safe_area(self) -> tuple[int, int, int, int]:
        """Get safe drawing area (x, y, width, height)."""
        return (
            self.spacing.margin,
            self.spacing.margin,
            self.display.width - (2 * self.spacing.margin),
            self.display.height - (2 * self.spacing.margin),
        )

    @property
    def content_bounds(self) -> tuple[int, int]:
        """Get content area dimensions (width, height)."""
        return (self.layout.content_width, self.layout.content_height)

    def get_text_style(self, style_name: str) -> dict:
        """Get text style configuration by name."""
        return self.typography.styles.get(style_name, self.typography.styles["body"])

    def get_qr_size(self, size: str = "medium") -> int:
        """Get QR code size by name."""
        sizes = {
            "small": self.components.qr_small,
            "medium": self.components.qr_medium,
            "large": self.components.qr_large,
        }
        return sizes.get(size, self.components.qr_medium)


# Global theme instance
theme = Theme()
