# PFS Quicklook Web App

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Panel](https://img.shields.io/badge/Panel-1.8+-0091DA.svg)](https://panel.holoviz.org/)
[![HoloViews](https://img.shields.io/badge/HoloViews-1.18+-A61C3C.svg)](https://holoviews.org/)
[![GitHub issues](https://img.shields.io/github/issues/Subaru-SciOp/pfs_quicklook.svg)](https://github.com/Subaru-SciOp/pfs_quicklook/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/Subaru-SciOp/pfs_quicklook.svg)](https://github.com/Subaru-SciOp/pfs_quicklook/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/Subaru-SciOp/pfs_quicklook.svg)](https://github.com/Subaru-SciOp/pfs_quicklook/stargazers)

Web application for quick-look visualization of Prime Focus Spectrograph (PFS) data, designed for summit and remote observers to perform real-time quality assessment during observations.

This app replaces the previous Jupyter notebook-based quicklook tool ([check_quick_reduction_data.ipynb](legacy/check_quick_reduction_data.ipynb)) with a production-ready web interface.

[![1D Gallery View](docs/img/screenshot_pfsmerged.png)](docs/img/screenshot_pfsmerged.png)

## Key Features

- **Fiber configuration viewer** with interactive table and checkbox selection
- **Three-way fiber selection**: Select fibers via table, OB Code, or Fiber ID widgets
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

This software is licensed under the MIT License. See [LICENSE](LICENSE) for details.

Copyright (c) 2025 Masato Onodera, Subaru/PFS obsproc team

## Acknowledgments

Built with Panel, HoloViews, Bokeh, and the LSST Science Pipelines.
