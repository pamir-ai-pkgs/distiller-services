# Fonts Directory

This directory contains fonts used by the e-ink display functionality.

## MartianMono Font

The application looks for `MartianMonoNerdFont-CondensedBold.ttf` in this directory for optimal
display quality on e-ink screens.

### Installing the Font

1. Download MartianMono Nerd Font from
   [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts/releases)
2. Extract the font files
3. Copy `MartianMonoNerdFont-CondensedBold.ttf` to this directory

### Font Fallbacks

If the MartianMono font is not available, the application will fall back to:

1. Liberation fonts (`/usr/share/fonts/truetype/liberation/`)
2. System Arial fonts (on macOS)
3. Default system fonts

### Package Installation

When installing via the Debian package, this directory is created automatically at
`/opt/distiller-cm5-services/fonts/`.

The package includes the `fonts-liberation` package as a recommendation to ensure fallback fonts are
available.
