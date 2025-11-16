# PFS Quicklook Web App

Web application for quick-look visualization of Prime Focus Spectrograph (PFS) data, designed for summit and remote observers to perform real-time quality assessment during observations.

This app replaces the previous Jupyter notebook-based quicklook tool ([check_quick_reduction_data.ipynb](legacy/check_quick_reduction_data.ipynb)) with a production-ready web interface.

[![1D Gallery View](../img/screenshot_pfsmerged.png)](../img/screenshot_pfsmerged.png)

## Key Features

- **Fiber configuration viewer** with interactive table showing pointing and fiber details
- **Interactive 2D/1D spectral visualization** with zoom, pan, and hover tools
- **Multi-user support** with per-session state isolation
- **Automatic visit discovery** with configurable auto-refresh
- **Performance optimizations** (parallel processing, intelligent caching)
- **Dual deployment modes** (development/production)

## Prerequisites

- Access to PFSA servers
- Configuration file for Butler database access (contact Moritani-san, Yabe-san, or PFS obsproc team)

## Quick Start

```bash
# Clone repository
git clone https://github.com/Subaru-SciOp/pfs_quicklook.git
cd pfs_quicklook

# Follow setup guide for detailed installation
# See: docs/setup.md

# Launch application (production mode)
bash ./launch_app.bash

# Access in browser
# http://<your_server_hostname>:5106/quicklook
```

For detailed installation instructions, see **[Setup Guide](docs/setup.md)**.

## Documentation

### For Observers

Operating instructions for using the application during observations:

- **[User Guide](docs/user-guide/index.md)** - Complete workflow and features
  - [Loading Visit Data](docs/user-guide/loading-data.md)
  - [2D Spectral Images](docs/user-guide/2d-images.md)
  - [1D Spectra Visualization](docs/user-guide/1d-spectra.md)

### For Administrators

Installation, configuration, and maintenance:

- **[Setup Guide](docs/setup.md)** - Installation and deployment instructions

### For Everyone

- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions
- **[Documentation Index](docs/README.md)** - Complete documentation navigation

### For Developers

Technical details and architecture:

- **[CLAUDE.md](CLAUDE.md)** - Comprehensive technical documentation
  - Architecture and code organization
  - Performance optimization details
  - Development roadmap

## TODO

### High Priority

- DetectorMap overlay for fiber trace visualization
- Multi-visit stacking for improved S/N

### Medium Priority

- Export functionality (PNG, HTML, FITS)
- Additional visualization options (colormap selection, custom scaling)
- Advanced spectral analysis tools (line identification, measurements)

## Contact & Support

This is a QuickLook tool for PFS observatory operations.

**For issues or feature requests**:

- **PFS Observation Helpdesk**: <pfs-obs-help@naoj.org>
- **GitHub Issues**: <https://github.com/Subaru-SciOp/pfs_quicklook/issues>
- Review documentation: [User Guide](docs/user-guide/index.md) | [Troubleshooting](docs/troubleshooting.md)

## License

This software is developed for the Prime Focus Spectrograph (PFS) project.

## Acknowledgments

Built with Panel, HoloViews, Bokeh, and the LSST Science Pipelines.
