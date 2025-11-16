# Legacy Jupyter Notebook

This directory contains the original Jupyter notebook-based quicklook tool that has been replaced by the web application.

## Files

- **[check_quick_reduction_data.ipynb](check_quick_reduction_data.ipynb)** - Original Jupyter notebook (6.2 MB with outputs)
- **[check_quick_reduction_data.py](check_quick_reduction_data.py)** - Notebook exported as Python script (471 lines)

## Status

**⚠️ DEPRECATED**: This notebook is no longer actively maintained. It is kept here for reference and historical purposes.

**Use the web app instead**: See [main README](../README.md) for the current production application.

## Features (Original Notebook)

The notebook provided:
- Single-visit 2D/1D spectral visualization
- Multi-visit stacking for improved S/N
- Interactive matplotlib plots with cursor support
- Comprehensive metadata display

## Why It Was Replaced

The web application provides significant improvements:

### Advantages of Web App
- ✅ **Multi-user support**: Per-session state isolation
- ✅ **No Jupyter required**: Browser-based interface
- ✅ **Better performance**: Parallel processing, intelligent caching
- ✅ **Production-ready**: Dual deployment modes, proper error handling
- ✅ **Auto-refresh**: Automatic visit discovery
- ✅ **Interactive UI**: Modern web interface with HoloViews/Bokeh

### What Was Lost
- ❌ Multi-visit stacking (planned for future web app release)
- ❌ Matplotlib cursor interaction (replaced with Bokeh hover tools)

## Code Metrics Comparison

```
Original notebook (check_quick_reduction_data.py):
  - Total: 471 lines
  - Real code: 292 lines
  - Comments: 101 lines
  - Docstrings: 0 lines

Web app (app.py + quicklook_core.py):
  - Total: 2,774 lines
  - Real code: ~1,800 lines
  - Comprehensive NumPy-style docstrings
  - Production-ready error handling
```

The web app is ~6× larger in code but provides ~15× more functionality when accounting for multi-user support, deployment infrastructure, and production features.

## Technical Details

For detailed technical comparison and development notes, see [CLAUDE.md](../CLAUDE.md) sections:
- Code Efficiency Analysis
- Original Source Reference

## Historical Context

This notebook was used during PFS commissioning and early operations. It served as the prototype for the current web application and validated the quicklook workflow that is now implemented in production.

**Last updated**: 2025-01-15 (moved to legacy directory)
