# PFS QuickLook Documentation

Welcome to the PFS QuickLook documentation! This directory contains comprehensive guides for users, administrators, and developers.

## Documentation Index

### For Observers

If you're using PFS QuickLook to inspect spectral data during observations:

- **[User Guide](user-guide/index.md)** - Complete guide for operators
  - [Loading Visit Data](user-guide/loading-data.md) - How to load and select visits
  - [2D Spectral Images](user-guide/2d-images.md) - Working with 2D visualizations
  - [1D Spectra](user-guide/1d-spectra.md) - Viewing and analyzing 1D spectra

### For Administrators (e.g., Support Astronomers)

If you're installing, configuring, or maintaining PFS QuickLook:

- **[Setup Guide](setup.md)** - Installation and configuration instructions
  - Prerequisites and server requirements
  - Step-by-step installation process
  - Environment configuration (`.env` file)
  - Deployment modes (development vs production)
  - Post-installation verification

### For Troubleshooting

- **[Troubleshooting Guide](troubleshooting.md)** - Common issues and solutions
  - Launch issues
  - Data loading problems
  - Visualization errors
  - Performance optimization
  - How to get help

### For Developers

- **[CLAUDE.md](../CLAUDE.md)** - Technical documentation
  - Project architecture and code organization
  - Development roadmap and completed features
  - Performance optimization details
  - Code metrics and design decisions
  - API documentation

## Quick Links

### Getting Started

**First-time users**:

1. Read [User Guide Overview](user-guide/index.md) for workflow introduction
2. Follow [Loading Visit Data](user-guide/loading-data.md) to get started
3. Keep [Troubleshooting](troubleshooting.md) handy for quick reference

**Administrators**:

1. Follow [Setup Guide](setup.md) for installation
2. Configure `.env` file with correct datastore and collection
3. Launch application and verify operation

### Common Tasks

- **Load and visualize data**: [User Guide](user-guide/index.md)
- **Fix "No visits found" error**: [Troubleshooting - No Visits Found](troubleshooting.md#no-visits-found)
- **Configure environment**: [Setup Guide - Configuration](setup.md#5-configure-environment-variables)
- **Switch deployment modes**: [Setup Guide - Deployment Modes](setup.md#deployment-modes)
- **Optimize performance**: [Troubleshooting - Performance Issues](troubleshooting.md#performance-issues)

## Screenshots

All screenshots referenced in the documentation are located in [`img/`](img/) directory:

- [`screenshot_loadvisit.png`](img/screenshot_loadvisit.png) - Load visit interface
- [`screenshot_2dimage.png`](img/screenshot_2dimage.png) - 2D spectral images
- [`screenshot_pfsmerged.png`](img/screenshot_pfsmerged.png) - 1D gallery view
- [`screenshot_1dspec.png`](img/screenshot_1dspec.png) - Individual 1D spectra

## Additional Resources

### Support

- **PFS Observation Helpdesk**: <pfs-obs-help@naoj.org>
- **GitHub Issues**: <https://github.com/Subaru-SciOp/pfs_quicklook/issues>
- **Main README**: [../README.md](../README.md)

### Development

- **Repository**: <https://github.com/Subaru-SciOp/pfs_quicklook>
- **Technical Docs**: [CLAUDE.md](../CLAUDE.md)
- **Original Notebook**: [check_quick_reduction_data.ipynb](../check_quick_reduction_data.ipynb)

## Documentation Maintenance

This documentation is maintained alongside the PFS QuickLook application code. If you find errors, outdated information, or have suggestions for improvement:

- Create an issue on GitHub: <https://github.com/Subaru-SciOp/pfs_quicklook/issues>
- Contact the development team
- Submit a pull request with corrections

**Last updated**: 2025-01-15
