# Setup Guide for Administrators

This guide provides detailed installation and configuration instructions for PFS QuickLook administrators.

## Prerequisites

You need to have access to one of PFSA servers to run this app. Also, you need a proper configuration file for database access. Please ask Moritani-san, Yabe-san, or other relevant PFS obsproc team members for the configuration file.

## Installation Steps

### 1. Activate LSST Stack Environment

```bash
source /work/stack/loadLSST.bash
```

This loads the LSST Science Pipelines environment which provides the core data processing libraries required by PFS QuickLook.

### 2. Clone the Repository

```bash
git clone https://github.com/Subaru-SciOp/pfs_quicklook.git
cd pfs_quicklook
```

### 3. Create Directory for Additional Python Packages

The LSST stack doesn't include all packages required for the web interface (Panel, HoloViews, etc.). Create a directory to install these additional packages:

```bash
mkdir -p /work/<your_username>/lsst-stack-local-pythonlibs
```

Replace `<your_username>` with your actual username.

### 4. Install Required Python Packages

```bash
# Verify you're using python3 from the LSST stack
which python3
# Should return something like: /work/stack-2025-06-06/conda/envs/lsst-scipipe-10.0.0/bin/python3

# Install packages to the custom directory
python3 -m pip install --target=/work/<your_username>/lsst-stack-local-pythonlibs -r requirements.txt
```

The required packages include:
- `panel` - Web framework for the application
- `holoviews` - Interactive visualization library
- `bokeh` - Plotting backend
- `datashader` - Fast rasterization for large datasets
- `watchfiles` - Auto-reload support for development
- `loguru` - Logging framework
- `joblib` - Parallel processing
- `python-dotenv` - Environment configuration

### 5. Configure Environment Variables

Create and configure the `.env` file:

```bash
cp .env.example .env
vi .env  # or use nano, emacs, etc.
```

Edit the following variables in the `.env` file:

```bash
# Datastore directory to fetch reduced data
PFS_DATASTORE="/work/datastore"

# Name of the base collection for the reduction
# This should be the collection name for the night you want to observe
# Example: u/obsproc/s25a/20250520b
PFS_BASE_COLLECTION="<collection_name_for_the_night>"

# Observation date to be considered
# Format: YYYY-MM-DD (e.g., 2025-05-26) or "TODAY" (automatically uses today's UTC date)
# Only single date is allowed
PFS_OBSDATE_UTC="TODAY"

# Auto-refresh interval for visit list (in seconds)
# Set to 0 to disable auto-refresh
# Default: 300 seconds (5 minutes)
PFS_VISIT_REFRESH_INTERVAL=300

# Hostname to run the app
# Full hostname can be obtained by running `hostname -f` command
# This is required for proper WebSocket configuration
PFS_APP_HOSTNAME=<your_server_hostname>

# Location of additional Python packages
# This directory contains packages installed with pip --target
LSST_PYTHON_USERLIB="/work/<your_username>/lsst-stack-local-pythonlibs"
```

#### Configuration Details

**PFS_DATASTORE**
- Path to the Butler datastore containing reduced PFS data
- Typically `/work/datastore` on PFSA servers
- Must be accessible from the server running the application

**PFS_BASE_COLLECTION**
- Base collection name for the observation night
- Format typically: `u/obsproc/<semester>/<date>` (e.g., `u/obsproc/s25a/20250520b`)
- Application will search for visit subcollections under this base collection
- Contact the PFS obsproc team for the correct collection name

**PFS_OBSDATE_UTC**
- Filters visits by observation date (UTC)
- Special value `"TODAY"` automatically uses current UTC date (recommended)
- Can also specify explicit date: `"2025-05-26"`
- Only visits matching this date will be shown in the visit list
- Configuration reloaded on each browser session start

**PFS_VISIT_REFRESH_INTERVAL**
- How often to check for new visits (in seconds)
- Default: 300 seconds (5 minutes)
- Set to 0 to disable automatic refresh
- Shorter intervals provide more up-to-date visit list but increase server load
- Recommended: 300-600 seconds for production use

**PFS_APP_HOSTNAME**
- Full hostname of the server running the application
- Required for WebSocket origin validation
- Get your hostname with: `hostname -f`
- Launch script validates this matches actual hostname before starting
- Prevents accidental launches on wrong server

**LSST_PYTHON_USERLIB**
- Path to directory created in step 3
- Contains Panel and other dependencies not in LSST stack
- Added to PYTHONPATH by launch script

### 6. Launch the Application

It's recommended to run the application inside a `tmux` session so it continues running after you disconnect:

```bash
# Start a tmux session (optional but recommended)
tmux new -s pfs_quicklook

# Launch the application
bash ./launch_app.bash

# Detach from tmux: Ctrl+B, then D
# Reattach later: tmux attach -t pfs_quicklook
```

**Tip**: For more tmux commands and shortcuts, see the [tmux cheatsheet](https://tmuxcheatsheet.com/).

The launch script automatically:
1. Validates hostname matches `PFS_APP_HOSTNAME`
2. Loads LSST environment
3. Sets up PFS pipeline packages
4. Configures Python path for additional packages
5. Selects deployment mode (development or production)
6. Launches Panel server with appropriate settings

#### Deployment Modes

**Production Mode** (default):
```bash
bash ./launch_app.bash
# or explicitly:
bash ./launch_app.bash production
```
- Port: 5106
- Multi-threaded (`--num-threads 8`) for concurrent users
- No auto-reload (stable for production)
- Access: `http://<your_server_hostname>:5106/quicklook`

**Development Mode**:
```bash
bash ./launch_app.bash dev
```
- Port: 5206
- Auto-reload on code changes (`--dev` flag)
- Single-threaded
- Access: `http://<your_server_hostname>:5206/quicklook`

### 7. Access the Application

Once launched, access the application from your web browser:

**Production mode** (default):
```
http://<your_server_hostname>:5106/quicklook
```

**Development mode**:
```
http://<your_server_hostname>:5206/quicklook
```

Replace `<your_server_hostname>` with the actual hostname configured in `.env`.

## Post-Installation

### Verify Installation

1. Check that the application loads without errors
2. Verify configuration display in sidebar shows correct values
3. Confirm visit list populates (may take 10-20 seconds on first load)
4. Test loading a visit and creating plots

### Regular Maintenance

- **Update `.env`** as needed for different observation nights (change `PFS_BASE_COLLECTION`)
- **Monitor application logs** for errors or performance issues
- **Update dependencies** periodically: re-run `pip install` command from step 4
- **Check disk space** in datastore and temp directories

### Updating the Application

```bash
cd /path/to/pfs_quicklook
git pull
# Reinstall dependencies if requirements.txt changed
python3 -m pip install --target=/work/<your_username>/lsst-stack-local-pythonlibs -r requirements.txt
# Restart the application
```

## Troubleshooting Installation Issues

### "Hostname mismatch" Error

**Symptom**: Launch script fails with hostname mismatch message

**Solution**:
1. Check current hostname: `hostname -f`
2. Update `PFS_APP_HOSTNAME` in `.env` to match
3. Relaunch application

### Import Errors

**Symptom**: Python import errors when launching

**Solution**:
1. Verify LSST stack is loaded: `source /work/stack/loadLSST.bash`
2. Check Python path includes custom library: `echo $PYTHONPATH`
3. Verify packages installed correctly in custom directory
4. Re-run pip install command from step 4

### Butler Configuration Errors

**Symptom**: "Cannot access datastore" or similar Butler errors

**Solution**:
1. Verify `PFS_DATASTORE` path exists and is accessible
2. Check `PFS_BASE_COLLECTION` is correct (ask PFS obsproc team)
3. Ensure you have read permissions for datastore directory
4. Test Butler access manually using `butler` command-line tool

### Package Installation Fails

**Symptom**: pip install fails with permission errors

**Solution**:
1. Do NOT use `sudo` - should install to user directory only
2. Verify you're using LSST stack Python: `which python3`
3. Check `--target` path is writable by your user
4. Try installing packages one at a time to identify problematic package

### Port Already in Use

**Symptom**: "Address already in use" error on launch

**Solution**:
1. Check if application is already running: `ps aux | grep panel`
2. Kill existing process: `pkill -f "panel serve"`
3. Or use different port by modifying launch script
4. Ensure firewall allows traffic on chosen port

## Performance Tuning

### For High-Traffic Scenarios

If you expect many concurrent users:

1. **Increase thread count** in production mode (edit [launch_app.bash](../launch_app.bash)):
   ```bash
   --num-threads 16  # Increase from default 8
   ```

2. **Adjust auto-refresh interval** in `.env`:
   ```bash
   PFS_VISIT_REFRESH_INTERVAL=600  # Reduce frequency for lower load
   ```

3. **Monitor server resources**:
   - CPU usage (`top` or `htop`)
   - Memory usage
   - Network bandwidth

### For Slow Visit Discovery

If visit discovery takes too long:

1. **Verify date filtering** is enabled (`PFS_OBSDATE_UTC` is set)
2. **Check network latency** to datastore
3. **Reduce collection size** by using night-specific collections
4. Visit discovery uses caching - first run is slow, subsequent refreshes are fast

## See Also

- [User Guide](user-guide/index.md) - How to use the application
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [CLAUDE.md](../CLAUDE.md) - Technical documentation for developers
